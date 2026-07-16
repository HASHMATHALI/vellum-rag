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
          50: '#fafafa',
          100: '#f4f4f5',
          200: '#e4e4e7',
          300: '#d4d4d8',
          400: '#a1a1aa',
          500: '#18181b', // Zinc 900
          600: '#09090b', // Zinc 950
          700: '#71717a',
          800: '#52525b',
          900: '#3f3f46',
        },
        dark: {
          bg: '#121214',       // Soft Charcoal (Lite Dark Mode)
          card: '#18181c',     // Clean Dark Slate Card
          border: '#27272a',   // Zinc-800 border line
          muted: '#a1a1aa'     // Zinc-400 Muted text
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
