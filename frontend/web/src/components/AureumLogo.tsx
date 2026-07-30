interface AureumLogoProps {
  className?: string;
  showWordmark?: boolean;
  size?: number;
}

export default function AureumLogo({
  className = "",
  showWordmark = true,
  size = 40,
}: AureumLogoProps) {
  return (
    <div className={`flex items-center gap-3 ${className}`}>
      <svg
        width={size}
        height={size}
        viewBox="0 0 100 100"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="shrink-0"
      >
        {
          /* Stylized interwoven A mark */
        }
        <path
          d="M50 8 L88 82 H72 L62 62 H38 L28 82 H12 L50 8 Z"
          stroke="#C9A227"
          strokeWidth="4"
          fill="none"
          strokeLinejoin="round"
        />
        <path
          d="M50 28 L66 58 H34 L50 28 Z"
          stroke="#C9A227"
          strokeWidth="3"
          fill="none"
          strokeLinejoin="round"
        />
        <path
          d="M20 82 Q50 55 80 35"
          stroke="#C9A227"
          strokeWidth="3"
          fill="none"
          strokeLinecap="round"
        />
      </svg>
      {showWordmark && (
        <span className="font-display text-2xl font-medium tracking-wide text-aureum-gold">
          AUREUM
        </span>
      )}
    </div>
  );
}
