import { useState, useRef, useEffect } from 'react';

interface ScrollHintProps {
  children: React.ReactNode;
  className?: string;
}

export function ScrollHint({ children, className }: ScrollHintProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [canScroll, setCanScroll] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const check = () => setCanScroll(el.scrollWidth > el.clientWidth);
    check();

    const observer = new ResizeObserver(check);
    observer.observe(el);
    return () => observer.disconnect();
  }, [children]);

  return (
    <div className="relative">
      <div ref={ref} className={`overflow-x-auto ${className ?? ''}`}>
        {children}
      </div>
      {canScroll && (
        <div className="pointer-events-none absolute inset-y-0 right-0 w-8 bg-gradient-to-l from-background to-transparent md:hidden" />
      )}
    </div>
  );
}
