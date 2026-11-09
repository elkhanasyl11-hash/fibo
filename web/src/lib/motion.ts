// Motion tokens (motion-foundations). Components import values from here, never inline numbers.

export const motionTokens = {
  duration: { instant: 0.08, fast: 0.18, normal: 0.35, slow: 0.6, crawl: 1.0 },
  easing: {
    smooth: [0.22, 1, 0.36, 1] as const,
    sharp: [0.4, 0, 0.2, 1] as const,
    linear: [0, 0, 1, 1] as const,
  },
  distance: { xs: 4, sm: 8, md: 16, lg: 24, xl: 48 },
  scale: { subtle: 0.98, press: 0.97, pop: 1.02 },
  stagger: 0.06,
}

export const springs = {
  snappy: { type: "spring", stiffness: 300, damping: 30 },
  gentle: { type: "spring", stiffness: 140, damping: 20 },
  instant: { type: "spring", stiffness: 600, damping: 35 },
  release: { type: "spring", stiffness: 200, damping: 20, restDelta: 0.001 },
} as const
