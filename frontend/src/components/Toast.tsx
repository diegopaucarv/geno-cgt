import { useEffect, useState } from "react";

interface ToastProps {
  message: string;
  visible: boolean;
  onDone: () => void;
}

export function Toast({ message, visible, onDone }: ToastProps) {
  const [fade, setFade] = useState<"in" | "out" | "hidden">("hidden");

  useEffect(() => {
    if (visible) {
      setFade("in");
      const t1 = setTimeout(() => setFade("out"), 2500);
      const t2 = setTimeout(() => {
        setFade("hidden");
        onDone();
      }, 3000);
      return () => {
        clearTimeout(t1);
        clearTimeout(t2);
      };
    }
  }, [visible, onDone]);

  if (fade === "hidden") return null;

  return (
    <div
      style={{
        position: "fixed",
        bottom: 24,
        left: "50%",
        transform: "translateX(-50%)",
        zIndex: 999,
        padding: "10px 24px",
        borderRadius: 8,
        background: "#D29922",
        color: "#0D1117",
        fontSize: 13,
        fontWeight: 600,
        boxShadow: "0 4px 24px rgba(210,153,34,0.4)",
        opacity: fade === "in" ? 1 : 0,
        transition: "opacity 0.5s ease",
        pointerEvents: "none",
      }}
    >
      {message}
    </div>
  );
}
