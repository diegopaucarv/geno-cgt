import { useEffect, useState } from "react";

interface ToastProps {
  message: string;
  visible: boolean;
  type?: "info" | "error";
  onDone: () => void;
}

export function Toast({ message, visible, type = "info", onDone }: ToastProps) {
  const [fade, setFade] = useState<"in" | "out" | "hidden">("hidden");

  useEffect(() => {
    if (visible) {
      setFade("in");
      const duration = type === "error" ? 6000 : 2500;
      const t1 = setTimeout(() => setFade("out"), duration);
      const t2 = setTimeout(() => {
        setFade("hidden");
        onDone();
      }, duration + 500);
      return () => {
        clearTimeout(t1);
        clearTimeout(t2);
      };
    }
  }, [visible, onDone, type]);

  if (fade === "hidden") return null;

  const isError = type === "error";

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
        background: isError ? "#F85149" : "#D29922",
        color: isError ? "#FFF" : "#0D1117",
        fontSize: 13,
        fontWeight: 600,
        boxShadow: isError
          ? "0 4px 24px rgba(248,81,73,0.5)"
          : "0 4px 24px rgba(210,153,34,0.4)",
        opacity: fade === "in" ? 1 : 0,
        transition: "opacity 0.5s ease",
        pointerEvents: "none",
        maxWidth: "80vw",
        textAlign: "center",
      }}
    >
      {isError && "❌ "}
      {message}
    </div>
  );
}
