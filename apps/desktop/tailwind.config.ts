import type { Config } from 'tailwindcss';

export default {
  content: ['./src/**/*.{html,js,svelte,ts}'],
  theme: {
    extend: {
      colors: {
        isotope: {
          bg: '#f7f1e3',
          canvas: '#f7f1e3',
          panel: '#fffcf4',
          'panel-raised': '#fff8ec',
          text: '#202020',
          ink: '#202020',
          rail: '#2b251f',
          muted: '#7d7467',
          line: '#d6cdbd',
          'line-strong': '#bdb4a4',
          red: '#c9342c',
          'red-dark': '#8f1512',
          yellow: '#e2b631',
          'yellow-surface': '#fff2c8',
          blue: '#1d58a8',
          'blue-surface': '#edf3f9',
          umber: '#9a4f1c',
          green: '#26734d',
          'green-surface': '#e8f3ea',
          attention: '#c9342c',
          running: '#1d58a8',
          warning: '#e2b631',
          done: '#26734d',
          error: '#c9342c'
        }
      },
      borderRadius: {
        panel: '6px'
      }
    }
  },
  plugins: []
} satisfies Config;
