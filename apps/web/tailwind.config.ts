import type { Config } from 'tailwindcss'

const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // 主色系
        midas: {
          red: '#C8102E',
          'red-deep': '#9E1024',
          'red-soft': '#E84560',
          'red-glow': 'rgba(200,16,46,0.06)',
          'red-tint': 'rgba(200,16,46,0.12)',
        },
        gold: {
          DEFAULT: '#B8860B',
          soft: '#D4A72C',
          glow: 'rgba(184,134,11,0.08)',
        },
        // 中性
        ink: {
          DEFAULT: '#1A1A1A',
          dim: '#5A5A62',
          faint: '#94949C',
        },
        // 背景
        paper: '#F7F6F1',
        cream: '#FCFCF9',
        // 涨跌(A 股传统)
        bull: '#DC143C',
        bear: '#0F6E5F',
        // 警告 / 警示
        warn: '#B45309',
      },
      fontFamily: {
        serif: ['"Noto Serif SC"', 'serif'],
        sans: ['"Noto Sans SC"', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
      },
      borderRadius: {
        sm: '2px',
        DEFAULT: '4px',
        md: '6px',
        lg: '8px',
      },
    },
  },
  plugins: [],
}

export default config
