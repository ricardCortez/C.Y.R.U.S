/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        cyrus: {
          bg:      '#040d1a',
          panel:   '#071224',
          border:  '#0a4060',
          cyan:    '#00d4ff',
          blue:    '#0088ff',
          glow:    '#00ffff',
          dim:     '#004060',
          text:    '#b0e8ff',
          muted:   '#406080',
          error:   '#ff4444',
          success: '#00ff88',
        },
      },
      fontFamily: {
        mono: ['"Share Tech Mono"', '"Courier New"', 'monospace'],
        sans: ['"Exo 2"', '"Segoe UI"', 'sans-serif'],
      },
      boxShadow: {
        'cyrus-glow': '0 0 20px rgba(0, 212, 255, 0.3)',
        'cyrus-strong': '0 0 40px rgba(0, 212, 255, 0.6)',
        'cyrus-panel': 'inset 0 0 30px rgba(0, 136, 255, 0.1)',
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'scan': 'scan 4s linear infinite',
        'flicker': 'flicker 0.15s infinite',
        'orbit': 'orbit 8s linear infinite',
      },
      keyframes: {
        scan: {
          '0%': { transform: 'translateY(-100%)' },
          '100%': { transform: 'translateY(100vh)' },
        },
        flicker: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.85' },
        },
        orbit: {
          '0%': { transform: 'rotate(0deg) translateX(80px) rotate(0deg)' },
          '100%': { transform: 'rotate(360deg) translateX(80px) rotate(-360deg)' },
        },
      },
    },
  },
  plugins: [],
}
