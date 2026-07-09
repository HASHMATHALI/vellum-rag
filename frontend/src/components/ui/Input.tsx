import React from 'react';

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helperText?: string;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(({
  label,
  error,
  helperText,
  className = '',
  id,
  type = 'text',
  ...props
}, ref) => {
  return (
    <div className="flex flex-col gap-1.5 w-full">
      {label && (
        <label htmlFor={id} className="text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-dark-muted">
          {label}
        </label>
      )}
      <input
        ref={ref}
        id={id}
        type={type}
        className={`
          px-4 py-2.5 rounded-xl border border-gray-300 dark:border-dark-border 
          bg-white dark:bg-dark-bg text-sm
          placeholder:text-gray-400 dark:placeholder:text-dark-muted
          focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500
          disabled:opacity-50 disabled:bg-gray-100 dark:disabled:bg-gray-900
          transition-all ${error ? 'border-red-500 focus:ring-red-500/20 focus:border-red-500' : ''} ${className}
        `}
        {...props}
      />
      {error ? (
        <span className="text-xs font-semibold text-red-500">{error}</span>
      ) : helperText ? (
        <span className="text-xs text-gray-500 dark:text-dark-muted">{helperText}</span>
      ) : null}
    </div>
  );
});

Input.displayName = 'Input';


