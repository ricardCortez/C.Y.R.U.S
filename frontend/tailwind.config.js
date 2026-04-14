// frontend/tailwind.config.js
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        orbitron: ['Orbitron', 'sans-serif'],
        mono: ['Share Tech Mono', 'monospace'],
      },
      colors: {
        primary:   '#00f0ff',
        secondary: '#0077ff',
        bg:        '#05070d',
        warn:      '#ff8c00',
        danger:    '#ff3333',
        ok:        '#00ff88',
      },
    },
  },
  plugins: [],
}
