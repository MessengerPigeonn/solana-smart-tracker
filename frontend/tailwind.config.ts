import type { Config } from "tailwindcss";

const config: Config = {
    darkMode: ["class"],
    content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
  	extend: {
  		fontFamily: {
  			body: ['var(--font-body)', 'system-ui', 'sans-serif'],
  			mono: ['var(--font-mono)', 'ui-monospace', 'monospace'],
  		},
  		colors: {
  			background: 'hsl(var(--background))',
  			foreground: 'hsl(var(--foreground))',
  			card: {
  				DEFAULT: 'hsl(var(--card))',
  				foreground: 'hsl(var(--card-foreground))'
  			},
  			popover: {
  				DEFAULT: 'hsl(var(--popover))',
  				foreground: 'hsl(var(--popover-foreground))'
  			},
  			primary: {
  				DEFAULT: 'hsl(var(--primary))',
  				foreground: 'hsl(var(--primary-foreground))'
  			},
  			secondary: {
  				DEFAULT: 'hsl(var(--secondary))',
  				foreground: 'hsl(var(--secondary-foreground))'
  			},
  			muted: {
  				DEFAULT: 'hsl(var(--muted))',
  				foreground: 'hsl(var(--muted-foreground))'
  			},
  			accent: {
  				DEFAULT: 'hsl(var(--accent))',
  				foreground: 'hsl(var(--accent-foreground))'
  			},
  			destructive: {
  				DEFAULT: 'hsl(var(--destructive))',
  				foreground: 'hsl(var(--destructive-foreground))'
  			},
  			border: 'hsl(var(--border))',
  			input: 'hsl(var(--input))',
  			ring: 'hsl(var(--ring))',
  			chart: {
  				'1': 'hsl(var(--chart-1))',
  				'2': 'hsl(var(--chart-2))',
  				'3': 'hsl(var(--chart-3))',
  				'4': 'hsl(var(--chart-4))',
  				'5': 'hsl(var(--chart-5))'
  			},
  			teal: {
  				DEFAULT: '#24dbc9',
  				light: '#3dd6f5',
  				dark: '#1ab5a5',
  			},
  		},
  		borderRadius: {
  			lg: 'var(--radius)',
  			md: 'calc(var(--radius) - 2px)',
  			sm: 'calc(var(--radius) - 4px)'
  		},
  		animation: {
  			'pulse-glow': 'pulse-glow 2s ease-in-out infinite',
  			'float': 'float 3s ease-in-out infinite',
  			'blink': 'blink 1.5s ease-in-out infinite',
  			'fade-in': 'fadeIn 0.3s ease-out',
  			'slide-up': 'slideUp 0.4s ease-out',
  		},
  		keyframes: {
  			'pulse-glow': {
  				'0%, 100%': { boxShadow: '0 0 20px rgba(36,219,201,0.3), 0 0 40px rgba(36,219,201,0.1)' },
  				'50%': { boxShadow: '0 0 30px rgba(36,219,201,0.5), 0 0 60px rgba(36,219,201,0.2)' },
  			},
  			float: {
  				'0%, 100%': { transform: 'translateY(0)' },
  				'50%': { transform: 'translateY(-6px)' },
  			},
  			blink: {
  				'0%, 100%': { opacity: '1' },
  				'50%': { opacity: '0.3' },
  			},
  			fadeIn: {
  				from: { opacity: '0' },
  				to: { opacity: '1' },
  			},
  			slideUp: {
  				from: { opacity: '0', transform: 'translateY(8px)' },
  				to: { opacity: '1', transform: 'translateY(0)' },
  			},
  		},
  	}
  },
  plugins: [require("tailwindcss-animate")],
};
export default config;
