import React from 'react';

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  glass?: boolean;
  hoverEffect?: boolean;
}

export const Card: React.FC<CardProps> = ({
  children,
  glass = false,
  hoverEffect = false,
  className = '',
  ...props
}) => {
  return (
    <div
      className={`
        rounded-2xl border border-gray-200/50 dark:border-white/5 
        ${glass ? 'glass' : 'bg-white dark:bg-dark-card'} 
        ${hoverEffect ? 'hover:shadow-lg dark:hover:shadow-brand-500/5 hover:-translate-y-0.5 transition-all duration-200' : ''} 
        ${className}
      `}
      {...props}
    >
      {children}
    </div>
  );
};


