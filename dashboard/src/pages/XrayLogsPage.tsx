import { Box, VStack, Text, Select, Stack, useColorMode, useColorModeValue, chakra } from "@chakra-ui/react";
import { useNodesQuery } from "contexts/NodesContext";
import { FC, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import useWebSocket from "react-use-websocket";
import { getAuthToken } from "utils/authStorage";
import { joinPaths } from "@remix-run/router";
import { debounce } from "lodash";
import useGetUser from "hooks/useGetUser";

const MAX_NUMBER_OF_LOGS = 500;

const getWebsocketUrl = (nodeID: string) => {
  try {
    let baseURL = new URL(
      import.meta.env.VITE_BASE_API.startsWith("/")
        ? window.location.origin + import.meta.env.VITE_BASE_API
        : import.meta.env.VITE_BASE_API
    );

    return (
      (baseURL.protocol === "https:" ? "wss://" : "ws://") +
      joinPaths([
        baseURL.host + baseURL.pathname,
        !nodeID ? "/core/logs" : `/node/${nodeID}/logs`,
      ]) +
      "?interval=1&token=" +
      getAuthToken()
    );
  } catch (e) {
    console.error("Unable to generate websocket url");
    console.error(e);
    return null;
  }
};

interface XrayLogsPageProps {
  showTitle?: boolean;
}

export const XrayLogsPage: FC<XrayLogsPageProps> = ({ showTitle = true }) => {
  const { t } = useTranslation();
  const { userData, getUserIsSuccess } = useGetUser();
  const canViewXrayLogs =
    getUserIsSuccess && Boolean(userData.permissions?.sections.xray);
  const { data: nodes } = useNodesQuery({ enabled: canViewXrayLogs });
  const [selectedNode, setNode] = useState<string>("");
  const [logs, setLogs] = useState<string[]>([]);
  const logsDiv = useRef<HTMLDivElement | null>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const { colorMode } = useColorMode();

  const handleLog = (id: string) => {
    if (id === selectedNode) return;
    if (!id) {
      setNode("");
      setLogs([]);
      return;
    }
    setNode(id);
    setLogs([]);
  };

  const appendLog = useCallback(
    debounce((line: string) => {
      setLogs((prev) => {
        const next =
          prev.length >= MAX_NUMBER_OF_LOGS
            ? [...prev.slice(prev.length - MAX_NUMBER_OF_LOGS + 1), line]
            : [...prev, line];
        return next;
      });
    }, 50),
    []
  );

  useEffect(() => {
    return () => {
      appendLog.cancel();
    };
  }, [appendLog]);

  const socketUrl = useMemo(
    () => (canViewXrayLogs ? getWebsocketUrl(selectedNode) : null),
    [canViewXrayLogs, selectedNode]
  );

  const { readyState } = useWebSocket(
    socketUrl,
    {
      onMessage: (e: any) => {
        appendLog(e.data ?? "");
      },
      shouldReconnect: () => Boolean(socketUrl),
      reconnectAttempts: 10,
      reconnectInterval: 1000,
    },
    Boolean(socketUrl)
  );

  useEffect(() => {
    const element = logsDiv.current;
    if (!element) return;
    const handleScroll = () => {
      const threshold = 32;
      const isAtBottom =
        element.scrollHeight - element.scrollTop - element.clientHeight <= threshold;
      setAutoScroll(isAtBottom);
    };
    element.addEventListener("scroll", handleScroll);
    handleScroll();
    return () => {
      element.removeEventListener("scroll", handleScroll);
    };
  }, []);

  useEffect(() => {
    if (autoScroll && logsDiv.current) {
      logsDiv.current.scrollTop = logsDiv.current.scrollHeight;
    }
  }, [logs, autoScroll]);

  const logPalette = useMemo(() => {
    const isDark = colorMode === "dark";
    return {
      error: {
        bg: isDark ? "rgba(239, 68, 68, 0.2)" : "rgba(254, 226, 226, 0.8)",
        color: isDark ? "#fca5a5" : "#dc2626",
        border: isDark ? "#ef4444" : "#dc2626",
      },
      warn: {
        bg: isDark ? "rgba(234, 179, 8, 0.2)" : "rgba(254, 243, 199, 0.8)",
        color: isDark ? "#fde047" : "#ca8a04",
        border: isDark ? "#eab308" : "#facc15",
      },
      info: {
        bg: isDark ? "rgba(34, 197, 94, 0.2)" : "rgba(209, 250, 229, 0.8)",
        color: isDark ? "#86efac" : "#16a34a",
        border: isDark ? "#22c55e" : "#22c55e",
      },
      debug: {
        bg: isDark ? "rgba(148, 163, 184, 0.16)" : "rgba(241, 245, 249, 0.8)",
        color: isDark ? "#cbd5e1" : "#475569",
        border: isDark ? "#94a3b8" : "#94a3b8",
      },
      default: {
        bg: isDark ? "rgba(51, 65, 85, 0.1)" : "rgba(248, 250, 252, 0.8)",
        color: isDark ? "#e2e8f0" : "#64748b",
        border: isDark ? "#475569" : "#cbd5e1",
      },
    };
  }, [colorMode]);

  const containerBg = useColorModeValue("#f5f7fb", "#1f2329");
  const containerBorder = useColorModeValue("gray.200", "gray.600");
  const badgeColor = useColorModeValue("gray.500", "gray.400");
  const selectBg = useColorModeValue("white", "gray.700");

  const classifyLog = (message: string) => {
    const lowerMessage = message.toLowerCase();
    // Check for error patterns first (most critical)
    if (/error|failed|exception|fatal|panic|critical/i.test(lowerMessage)) {
      return "error" as const;
    }
    // Check for warning patterns
    if (/warn|warning|deprecated/i.test(lowerMessage)) {
      return "warn" as const;
    }
    // Check for info patterns
    if (/info|information|success|connected|started|stopped/i.test(lowerMessage)) {
      return "info" as const;
    }
    // Check for debug patterns
    if (/debug|trace|verbose/i.test(lowerMessage)) {
      return "debug" as const;
    }
    return "default" as const;
  };

  if (!canViewXrayLogs) {
    return (
      <VStack spacing={4} align="stretch">
        {showTitle && (
          <Text as="h1" fontWeight="semibold" fontSize="2xl">
            {t("xrayLogs.title", "Xray logs")}
          </Text>
        )}
        <Text fontSize="sm" color="gray.500" _dark={{ color: "gray.400" }}>
          {t("xrayLogs.noPermission", "You do not have permission to view Xray logs.")}
        </Text>
      </VStack>
    );
  }

  return (
    <VStack spacing={6} align="stretch">
      {showTitle && (
        <Text as="h1" fontWeight="semibold" fontSize="2xl">
          {t("header.xrayLogs")}
        </Text>
      )}
      <Stack
        direction={{ base: "column", sm: "row" }}
        spacing={{ base: 3, sm: 4 }}
        align={{ base: "stretch", sm: "center" }}
        justify="space-between"
      >
        <Stack direction={{ base: "column", sm: "row" }} spacing={3} align={{ base: "stretch", sm: "center" }}>
          {nodes?.[0] && (
            <Select
              size="sm"
              w={{ base: "full", sm: "auto" }}
              bg={selectBg}
              onChange={(e) => handleLog(e.target.value)}
              value={selectedNode}
            >
              <option value="">{t("core.master")}</option>
              {nodes.map((s) => (
                <option key={s.address} value={String(s.id)}>
                  {t(s.name)}
                </option>
              ))}
            </Select>
          )}
          <Text fontSize="sm" color={badgeColor}>
            {t(`core.socket.${readyState}`)}
          </Text>
        </Stack>
        <Text fontSize="xs" color={badgeColor}>
          {autoScroll ? t("core.autoScrollOn", "Auto-scroll: On") : t("core.autoScrollOff", "Auto-scroll: Off")}
        </Text>
      </Stack>
      <Box
        border="1px solid"
        borderColor={containerBorder}
        bg={containerBg}
        borderRadius="lg"
        minHeight="200px"
        maxHeight="500px"
        p={3}
        overflowY="auto"
        ref={logsDiv}
        fontFamily="mono"
        fontSize="sm"
      >
        <VStack align="stretch" spacing={2}>
          {logs.map((message, i) => {
            const level = classifyLog(message);
            const palette = logPalette[level] ?? logPalette.default;
            return (
              <Box
                key={`${message}-${i}`}
                bg={palette.bg}
                color={palette.color}
                borderLeftWidth={3}
                borderLeftColor={palette.border}
                px={3}
                py={2}
                borderRadius="md"
                boxShadow="sm"
                _dark={{ boxShadow: "none" }}
              >
                <chakra.pre m={0} whiteSpace="pre-wrap" wordBreak="break-word">
                  {message}
                </chakra.pre>
              </Box>
            );
          })}
        </VStack>
      </Box>
    </VStack>
  );
};

export default XrayLogsPage;
