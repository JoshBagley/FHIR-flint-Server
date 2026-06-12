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
      aria-label="Flint-FHIR logo"
    >
      <defs>
        <linearGradient id="flint-bg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#2563eb" />
          <stop offset="100%" stopColor="#1e40af" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="7" fill="url(#flint-bg)" />
      {/* Vertical bar */}
      <rect x="13.5" y="6.5" width="5" height="19" rx="2" fill="white" />
      {/* Horizontal bar */}
      <rect x="6.5" y="13.5" width="19" height="5" rx="2" fill="white" />
      {/* Corner dots representing terminology codes */}
      <circle cx="7.5" cy="7.5" r="1.5" fill="white" opacity="0.4" />
      <circle cx="24.5" cy="7.5" r="1.5" fill="white" opacity="0.4" />
      <circle cx="7.5" cy="24.5" r="1.5" fill="white" opacity="0.4" />
      <circle cx="24.5" cy="24.5" r="1.5" fill="white" opacity="0.4" />
    </svg>
  );
}
