import React, { useRef, useState } from 'react';

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  glass?: boolean;
  hoverEffect?: boolean;
  spotlight?: boolean;
}

export const Card: React.FC<CardProps> = ({
  children,
  glass = false,
  hoverEffect = false,
  spotlight = true,
  className = '',
  ...props
}) => {
  const cardRef = useRef<HTMLDivElement>(null);
  const [coords, setCoords] = useState({ x: 0, y: 0 });
  const [isHovered, setIsHovered] = useState(false);

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!cardRef.current) return;
    const rect = cardRef.current.getBoundingClientRect();
    setCoords({
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
    });
  };

  const isDark = typeof document !== 'undefined' && document.documentElement.classList.contains('dark');
  const glowColor = isDark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(24, 24, 27, 0.03)';
  const borderGlowColor = isDark ? 'rgba(255, 255, 255, 0.15)' : 'rgba(24, 24, 27, 0.08)';

  return (
    <div
      ref={cardRef}
      onMouseMove={handleMouseMove}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      className={`
        relative rounded-2xl border border-gray-200/50 dark:border-white/5 
        overflow-hidden transition-all duration-300
        ${glass ? 'glass' : 'bg-white dark:bg-dark-card'} 
        ${hoverEffect ? 'hover:shadow-xl dark:hover:shadow-zinc-500/5 hover:-translate-y-0.5' : ''} 
        ${className}
      `}
      {...props}
    >
      {/* Spotlight Hover Glow Layer */}
      {spotlight && isHovered && (
        <div
          className="pointer-events-none absolute -inset-px transition-opacity duration-300"
          style={{
            background: `radial-gradient(350px circle at ${coords.x}px ${coords.y}px, ${glowColor}, transparent 85%)`,
          }}
        />
      )}
      
      {/* Spotlight Border Glow Layer */}
      {spotlight && isHovered && (
        <div
          className="pointer-events-none absolute inset-0 rounded-2xl border transition duration-300"
          style={{
            borderColor: 'transparent',
            background: `radial-gradient(120px circle at ${coords.x}px ${coords.y}px, ${borderGlowColor}, transparent) border-box`,
            mask: 'linear-gradient(#fff 0 0) padding-box, linear-gradient(#fff 0 0)',
            WebkitMask: 'linear-gradient(#fff 0 0) padding-box, linear-gradient(#fff 0 0)',
            maskComposite: 'exclude',
            WebkitMaskComposite: 'xor',
          }}
        />
      )}

      {/* Card Content Wrapper */}
      <div className="relative z-10 w-full h-full">
        {children}
      </div>
    </div>
  );
};
