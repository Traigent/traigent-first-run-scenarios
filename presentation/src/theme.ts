export const theme = {
  colors: {
    canvas: "080808",
    surface: "111214",
    surfaceRaised: "151922",
    blue: "1A6BF5",
    blueBright: "4D8EF8",
    green: "34D399",
    amber: "F59E0B",
    violet: "A78BFA",
    text: "F8FAFC",
    textSoft: "CBD5E1",
    muted: "94A3B8",
    border: "273244",
  },
  fonts: {
    sans: "Arial",
    mono: "Courier New",
  },
} as const;

export function toneColor(tone: "blue" | "green" | "amber" | "violet") {
  return {
    blue: theme.colors.blueBright,
    green: theme.colors.green,
    amber: theme.colors.amber,
    violet: theme.colors.violet,
  }[tone];
}
