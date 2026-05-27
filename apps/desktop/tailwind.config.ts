import type { Config } from 'tailwindcss';

export default {
  content: ['./src/**/*.{html,js,svelte,ts}'],
  theme: {
    extend: {
      colors: {
        isotope: {
          bg: '#f6f7f9',
          panel: '#ffffff',
          text: '#1f2933',
          muted: '#667085',
          line: '#d9dee7',
          attention: '#b42318',
          running: '#175cd3',
          done: '#067647'
        }
      },
      borderRadius: {
        panel: '6px'
      }
    }
  },
  plugins: []
} satisfies Config;
