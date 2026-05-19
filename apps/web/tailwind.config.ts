import type { Config } from 'tailwindcss'
import animate from 'tailwindcss-animate'

const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // ===== shadcn HSL token 桥接(从 globals.css CSS 变量读取)=====
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        card: {
          DEFAULT: 'hsl(var(--card))',
          foreground: 'hsl(var(--card-foreground))',
        },
        popover: {
          DEFAULT: 'hsl(var(--popover))',
          foreground: 'hsl(var(--popover-foreground))',
        },
        primary: {
          DEFAULT: 'hsl(var(--primary))',
          foreground: 'hsl(var(--primary-foreground))',
        },
        secondary: {
          DEFAULT: 'hsl(var(--secondary))',
          foreground: 'hsl(var(--secondary-foreground))',
        },
        muted: {
          DEFAULT: 'hsl(var(--muted))',
          foreground: 'hsl(var(--muted-foreground))',
        },
        accent: {
          DEFAULT: 'hsl(var(--accent))',
          foreground: 'hsl(var(--accent-foreground))',
        },
        destructive: {
          DEFAULT: 'hsl(var(--destructive))',
          foreground: 'hsl(var(--destructive-foreground))',
        },
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',

        // ===== 点金 Midas 品牌 token(Manus 原配,严禁改色值)=====
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
        ink: {
          DEFAULT: '#1A1A1A',
          dim: '#5A5A62',
          faint: '#94949C',
        },
        paper: '#F7F6F1',
        cream: '#FCFCF9',
        bull: '#DC143C',
        bear: '#0F6E5F',
        warn: '#B45309',
      },
      fontFamily: {
        serif: ['"Noto Serif SC"', 'serif'],
        sans: ['"Noto Sans SC"', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
      },
      borderRadius: {
        // Manus 原配:克制审慎,2/4/6/8 px 阶梯
        sm: '2px',
        DEFAULT: '4px',
        md: '6px',
        lg: '8px',
      },
    },
  },
  plugins: [animate],
}

export default config
