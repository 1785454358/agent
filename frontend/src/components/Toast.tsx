import { useEffect, useState } from "react";

/** 短暂错误提示条：5s 自动消失。 */
export function Toast({ message }: { message: string | null }) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (!message) return;
    setVisible(true);
    const timer = window.setTimeout(() => setVisible(false), 5_000);
    return () => window.clearTimeout(timer);
  }, [message]);

  if (!message || !visible) return null;
  return (
    <div className="toast" role="alert">
      {message}
    </div>
  );
}
