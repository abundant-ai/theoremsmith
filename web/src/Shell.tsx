import type { ReactNode } from "react";
import { Link as RouterLink } from "react-router-dom";
import { Box, Container, Flex, Heading, Text } from "@radix-ui/themes";

export default function Shell({ children }: { children: ReactNode }) {
  return (
    <Box className="ts-app">
      <Box style={{ borderBottom: "1px solid var(--gray-a4)", backdropFilter: "blur(6px)" }}>
        <Container size="4" px="5">
          <Flex align="baseline" gap="3" py="4" wrap="wrap">
            <Heading asChild size="5" weight="medium" style={{ letterSpacing: "-0.02em" }}>
              <RouterLink to="/" style={{ color: "var(--gray-12)", textDecoration: "none" }}>
                theoremsmith
              </RouterLink>
            </Heading>
            <Text size="2" color="gray">
              turns a Lean repository into a proof task
            </Text>
          </Flex>
        </Container>
      </Box>
      <Container size="4" px="5" py="7">
        {children}
      </Container>
    </Box>
  );
}
