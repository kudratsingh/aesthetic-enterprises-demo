/** Stand-ins removed as the Phase 2 royalty endpoints land (PR D wires them). */
export function Placeholder({ title }: { title: string }) {
  return (
    <>
      <h1>{title}</h1>
      <p className="hint">
        This screen activates when the Phase 2 royalty endpoints merge — the
        shell, routing, and auth are already live.
      </p>
    </>
  )
}
