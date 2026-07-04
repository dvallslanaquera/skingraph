// Shared line-icon set — one consistent family used across nav, buttons, chips,
// and empty states so the app reads as a single system. Thin-stroke SVGs in the
// landing page's botanical idiom: 24×24, currentColor stroke, ~1.9 weight,
// round caps/joins. Colour comes from the surrounding text colour (currentColor);
// size defaults to 24 and can be overridden per use.
import type { ReactNode, SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function Icon({ size = 24, children, ...rest }: IconProps & { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.9}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...rest}
    >
      {children}
    </svg>
  );
}

// Profile — a calm head-and-shoulders.
export function ProfileIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="12" cy="7.5" r="4" />
      <path d="M5 20.5v-1a5 5 0 0 1 5-5h4a5 5 0 0 1 5 5v1" />
    </Icon>
  );
}

// Routine — a skincare/serum bottle with a label band.
export function RoutineIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <rect x="9" y="2.5" width="6" height="3.2" rx="1" />
      <path d="M9.3 5.7 8.5 8.4A4 4 0 0 0 8 10.2V19a2 2 0 0 0 2 2h4a2 2 0 0 0 2-2v-8.8a4 4 0 0 0-.5-1.8l-.8-2.7" />
      <path d="M8 13h8" />
    </Icon>
  );
}

// Check — the scan viewfinder frame, reused verbatim from the landing hero.
export function CheckIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M3 9V7a2 2 0 0 1 2-2h2M17 5h2a2 2 0 0 1 2 2v2M21 15v2a2 2 0 0 1-2 2h-2M7 19H5a2 2 0 0 1-2-2v-2" />
      <circle cx="12" cy="12" r="3" />
    </Icon>
  );
}

// Camera — the capture/upload affordance (dropzones, "take a photo").
export function CameraIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3Z" />
      <circle cx="12" cy="13" r="3.2" />
    </Icon>
  );
}

// Clock — coach timing chip (AM/PM).
export function ClockIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7.5V12l3 1.8" />
    </Icon>
  );
}

// Repeat — coach frequency chip.
export function RepeatIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="m17 2 4 4-4 4" />
      <path d="M3 11v-1a4 4 0 0 1 4-4h14" />
      <path d="m7 22-4-4 4-4" />
      <path d="M21 13v1a4 4 0 0 1-4 4H3" />
    </Icon>
  );
}
