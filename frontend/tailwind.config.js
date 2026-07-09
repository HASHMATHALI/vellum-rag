/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class', // Enable class-based dark mode
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#f5f7ff',
          100: '#ebf0ff',
          200: '#dae3ff',
          300: '#bdcbff',
          400: '#94a9ff',
          500: '#637bff', // Core Brand Blue
          600: '#3d52f6',
          700: '#2a3ce3',
          800: '#2230bc',
          900: '#202b94',
        },
        dark: {
          bg: '#0B0F19',       // Deep visual dark blue background
          card: '#161F30',     // Contrasted card color
          border: '#23334E',   // Borders
          muted: '#6B7C97'     // Slate text
        }
      },
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
        display: ['Outfit', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
