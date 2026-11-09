import { Fragment } from "react"

// Assistant answers may use **bold** (Markdown). Render only that, as React text: no HTML injection.
export function RichText({ text }: { text: string }) {
  const parts = text.split(/(\*\*[^*\n]+\*\*)/g)
  return (
    <>
      {parts.map((part, i) =>
        part.startsWith("**") && part.endsWith("**") && part.length > 4 ? (
          <strong key={i} className="font-medium">
            {part.slice(2, -2)}
          </strong>
        ) : (
          <Fragment key={i}>{part.replace(/^#{1,6}\s+/gm, "")}</Fragment>
        )
      )}
    </>
  )
}
