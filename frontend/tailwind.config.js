/** @type {import('tailwindcss').Config} */

// "Vellum" identity: calfskin parchment and iron-gall ink.
// The UI is written almost entirely with zinc/gray utilities, so replacing
// those two scales re-tones every screen consistently without touching markup.
const vellum = {
  50: '#fbf7ee',   // fresh parchment
  100: '#f4eddc',
  200: '#e7dcc3',
  300: '#d3c4a3',
  400: '#a8987a',
  500: '#7d6f57',
  600: '#5c5140',
  700: '#40382c',
  800: '#2b2620',
  900: '#1c1915',  // iron-gall ink
  950: '#12100d',
};

export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class', // Enable class-based dark mode
  theme: {
    extend: {
      colors: {
        zinc: vellum,
        gray: vellum,
        white: '#fffdf8',
        // rubric red, the colour scribes used for headings and initials
        rubric: { DEFAULT: '#a3271f', light: '#d9584c' },
        brand: {
          50: vellum[50],
          100: vellum[100],
          200: vellum[200],
          300: vellum[300],
          400: vellum[400],
          500: vellum[900],
          600: vellum[950],
          700: vellum[500],
          800: vellum[600],
          900: vellum[700],
        },
        dark: {
          bg: '#15120f',
          card: '#1e1a16',
          border: '#342d25',
          muted: '#a8987a',
        }
      },
      fontFamily: {
        sans: ['"Albert Sans"', 'system-ui', 'sans-serif'],
        display: ['"Young Serif"', 'Georgia', 'serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'monospace'],
      },
      borderRadius: {
        // manuscripts have square corners: keep rounding slight everywhere
        lg: '4px', xl: '5px', '2xl': '6px', '3xl': '8px',
      },
    },
  },
  plugins: [],
}
