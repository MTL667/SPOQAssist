import { createLightTheme, BrandVariants, Theme } from "@fluentui/react-components";

/** SPOQ+ brand ramp (UX Visual Foundation) — scaffold baseline. */
const spoqBrand: BrandVariants = {
  10: "#061820",
  20: "#0B2E2A",
  30: "#0F4054",
  40: "#135067",
  50: "#1A6A82",
  60: "#2F9E7A",
  70: "#42AB9A",
  80: "#6BC4B5",
  90: "#9DD9CE",
  100: "#CDEFE0",
  110: "#DDF5EC",
  120: "#EAF8F3",
  130: "#F3F7FA",
  140: "#F8FBFC",
  150: "#FCFDFE",
  160: "#FFFFFF",
};

export const spoqTheme: Theme = {
  ...createLightTheme(spoqBrand),
  colorNeutralBackground1: "#F3F7FA",
  colorNeutralForeground1: "#1A2B33",
};
