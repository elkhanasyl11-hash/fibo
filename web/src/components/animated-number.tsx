import { animate, useReducedMotion } from "motion/react"
import { useEffect, useRef, useState } from "react"

import { motionTokens } from "@/lib/motion"

// A changed number tweens from its previous value (motion explains the change).
export function AnimatedNumber({ value, format }: { value: number; format: (v: number) => string }) {
  const reduce = useReducedMotion()
  const [shown, setShown] = useState(value)
  const previous = useRef(value)
  useEffect(() => {
    if (reduce) {
      previous.current = value
      return
    }
    const controls = animate(previous.current, value, {
      duration: motionTokens.duration.normal,
      ease: motionTokens.easing.smooth,
      onUpdate: setShown,
    })
    previous.current = value
    return () => controls.stop()
  }, [value, reduce])
  return <span className="num">{format(reduce ? value : shown)}</span>
}
