import type { Config } from 'tailwindcss'
import animate from 'tailwindcss-animate'

const config: Config = {
  darkMode: 'class',
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
        // ★暗黑 P0:容器/涨跌 primitives 转 CSS 变量(:root=原 light 值不变,.dark 补明度微调)
        paper: 'var(--midas-paper)',   // 原 #F7F6F1
        cream: 'var(--midas-cream)',   // 原 #FCFCF9
        bull: 'var(--midas-bull)',     // 原 #DC143C(涨朱红·暗底微调不翻转)
        bear: 'var(--midas-bear)',     // 原 #0F6E5F(跌墨绿·暗底微调不翻转)
        warn: 'var(--midas-warn)',     // 原 #B45309(警示琥珀·★P4 暗底提亮不翻转)

        // ===== 0022 语义层(业务代码引用这层;primitives 不再直接用)=====
        // 涨跌:只有 up/down 走 CSS 变量,支持「偏好开关」一处翻转全产品(0022 §2)
        up: 'var(--color-up)',
        down: 'var(--color-down)',
        // 动作(收口到 #C8102E · midas-red)
        'action-primary': '#C8102E',
        'action-hover': '#9E1024',
        'action-danger': '#C8102E', // 现与 primary 同值 · 独立命名留未来分色余地
        // 表面(收敛 cream 随机透明度 → 两档)· ★暗黑 P0 转变量(= cream/paper 同源)
        'surface-card': 'var(--midas-cream)', // = cream · 卡片/面板/弹窗实色
        'surface-subtle': 'var(--midas-paper)', // = paper · 表头/信号条/次级面板
        // 文字弱提示 / 状态
        faint: '#94949C', // = ink-faint · 占位/「—」/弱提示
        success: 'var(--midas-success)', // 原 #0F6E5F 独立成功绿(与 down 解耦不翻转·★P4 暗底提亮)
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
