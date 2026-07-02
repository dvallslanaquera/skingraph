// Reveals text progressively with a caret, like the coach typing their bottom
// line. Purely cosmetic and client-side: the full text is already in hand, so
// the reveal never delays the data (unlike a server-paced stream would).
import { useEffect, useState } from "react";

const CHARS_PER_TICK = 2;
const TICK_MS = 16;

export function Typewriter({
  text,
  className,
}: {
  text: string;
  className?: string;
}) {
  const [shown, setShown] = useState(0);

  useEffect(() => {
    setShown(0);
    if (!text) return;
    const id = window.setInterval(() => {
      setShown((n) => {
        if (n + CHARS_PER_TICK >= text.length) {
          window.clearInterval(id);
          return text.length;
        }
        return n + CHARS_PER_TICK;
      });
    }, TICK_MS);
    return () => window.clearInterval(id);
  }, [text]);

  return (
    <p className={className}>
      {text.slice(0, shown)}
      {shown < text.length && <span className="coach-caret">▍</span>}
    </p>
  );
}
