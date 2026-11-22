/** @type {import('tailwindcss').Config} */

// Dark-only identity built on three colours:
//   Gray   #2B2D31  surfaces
//   Silver #D9DADC  text
//   Yellow #FFC93C  accent (primary actions, highlights, active states)
// The UI is written almost entirely with zinc/gray utilities, so redefining those
// scales re-tones every screen consistently without touching markup.
const graphite = {
  50: '#F7F7F8',
  100: '#ECEDEE',
  200: '#D9DADC',  // silver: primary text
  300: '#BFC1C4',
  400: '#9A9DA2',
  500: '#76797F',
  600: '#55585E',
  700: '#3D4045',
  800: '#2B2D31',  // gray: cards and surfaces
  900: '#232528',
  950: '#1B1C1F',
};

const sun = {
  50: '#FFF9E6',
  100: '#FFF1C2',
  200: '#FFE699',
  300: '#FFDA6B',
  400: '#FFD150',
  500: '#FFC93C',  // yellow: accent
  600: '#F0B520',
  700: '#C99512',
  800: '#9C730E',
  900: '#6E510A',
};

export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class', // the `dark` class is always set on <html>
  theme: {
    extend: {
      colors: {
        zinc: graphite,
        gray: graphite,
        white: '#F7F7F8',
        brand: sun,
        // warnings (Gloss: unsupported / phantom citations), tuned for a dark background
        rubric: { DEFAULT: '#E5484D', light: '#FF8A8A' },
        dark: {
          bg: '#1E1F22',
          card: '#2B2D31',
          border: '#3A3D42',
          muted: '#9A9DA2',
        },
      },
      fontFamily: {
        sans: ['"Albert Sans"', 'system-ui', 'sans-serif'],
        display: ['"Albert Sans"', 'system-ui', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'monospace'],
      },
      borderRadius: {
        lg: '10px', xl: '14px', '2xl': '20px', '3xl': '28px',
      },
    },
  },
  plugins: [],
}
