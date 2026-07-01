interface AppLogoProps {
  size?: number;
  className?: string;
}

export default function AppLogo({ size = 36, className = '' }: AppLogoProps) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 32 32"
      width={size}
      height={size}
      className={className}
      aria-label="Flint logo"
    >
      <defs>
        <linearGradient id="flint-bg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#1e293b" />
          <stop offset="100%" stopColor="#0f172a" />
        </linearGradient>
        <linearGradient id="flint-flame" x1="0.3" y1="1" x2="0.6" y2="0">
          <stop offset="0%" stopColor="#b45309" />
          <stop offset="45%" stopColor="#f97316" />
          <stop offset="100%" stopColor="#fde68a" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="7" fill="url(#flint-bg)" />
      {/* FHIR-inspired flame with double peak */}
      <path
        d="M15 27C10.5 27 7 23.5 7 19.5C7 15.5 10 13 11 10C12 8 11 5.5 9.5 4C12.5 5.5 13.5 8.5 13.5 11C14 8.5 16 6 18.5 4.5C17.5 8 16 11 17 14C18 16.5 21 17.5 21 21C21 24.5 18 27 15 27Z"
        fill="url(#flint-flame)"
      />
      {/* Hot inner glow */}
      <path
        d="M15 24C13.5 24 12.5 22.5 12.5 21C12.5 19.5 13.5 18 14 16.5C14.5 18 14 19.5 15 20.5C15.5 19 16.5 17.5 17 16C17 18 16 19.5 16.5 21C17 22 17.5 23 16.5 23.5C16 24 15.5 24 15 24Z"
        fill="#fef9c3"
        opacity="0.85"
      />
      {/* Sparks */}
      <circle cx="22" cy="11" r="1.2" fill="#fbbf24" />
      <circle cx="24" cy="7" r="0.8" fill="#fde68a" />
      <circle cx="20.5" cy="5.5" r="0.9" fill="#fb923c" />
      <circle cx="8.5" cy="13.5" r="1" fill="#fb923c" />
      <circle cx="7" cy="10" r="0.7" fill="#fcd34d" />
      {/* Spark trails */}
      <line x1="21.5" y1="10.5" x2="23.5" y2="7.5" stroke="#fbbf24" strokeWidth="0.8" strokeLinecap="round" opacity="0.75" />
      <line x1="8.5" y1="13" x2="7" y2="10.5" stroke="#fb923c" strokeWidth="0.7" strokeLinecap="round" opacity="0.75" />
    </svg>
  );
}
