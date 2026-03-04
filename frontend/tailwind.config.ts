import type { Config } from 'tailwindcss';
import plugin from 'tailwindcss/plugin';

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ct: {
          bg: '#0a0e17',
          'bg-card': '#161b22',
          'bg-hover': '#1c2128',
          border: '#30363d',
          'border-hover': '#484f58',
          text: '#e1e4e8',
          'text-muted': '#8b949e',
          'text-dim': '#6e7681',
          accent: '#00d4aa',
          blue: '#0099ff',
          yellow: '#f0b429',
          red: '#f85149',
          green: '#3fb950',
        },
      },
      fontFamily: {
        sans: ['-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['SF Mono', 'Fira Code', 'Consolas', 'monospace'],
      },
    },
  },
  plugins: [
    plugin(function ({ addUtilities }) {
      addUtilities({
        '.pt-safe': { paddingTop: 'env(safe-area-inset-top)' },
        '.pb-safe': { paddingBottom: 'env(safe-area-inset-bottom)' },
        '.pl-safe': { paddingLeft: 'env(safe-area-inset-left)' },
        '.pr-safe': { paddingRight: 'env(safe-area-inset-right)' },
      });
    }),
  ],
} satisfies Config;
