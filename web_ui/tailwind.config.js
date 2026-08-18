/** @type {import('tailwindcss').Config} */
module.exports = {
  // 与线上一致：以 .dark 类切换暗色
  darkMode: 'class',
  // 扫描已发布的单页 HTML（含 <script> 内拼接的类名）
  content: ['./dist/index.html'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'PingFang SC', 'Microsoft YaHei', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
    },
  },
  // JS 中通过 classList.replace / 模板字符串动态拼接的类，确保不被 purge 掉
  safelist: [
    'bg-emerald-500',
    'bg-rose-500',
    'from-violet-400',
    'to-fuchsia-400',
  ],
  plugins: [],
};
