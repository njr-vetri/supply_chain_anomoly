/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: { extend: { colors: { ink: '#17233b', muted: '#71809a', line: '#e5eaf2', canvas: '#f5f7fb', brand: '#3157d5' }, boxShadow: { panel: '0 10px 30px rgba(27, 44, 80, .06)' } } },
  plugins: [],
}
