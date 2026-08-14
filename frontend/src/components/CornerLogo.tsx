import gosleulgosleulbibin from "../assets/corner-logos/gosleulgosleulbibin.png";
import dodamjjigae from "../assets/corner-logos/dodamjjigae.png";
import hansiksagye from "../assets/corner-logos/hansiksagye.png";
import dongbangsikgaek from "../assets/corner-logos/dongbangsikgaek.png";
import moderncuisine from "../assets/corner-logos/moderncuisine.png";
import xingfuchina from "../assets/corner-logos/xingfuchina.png";
import takeout from "../assets/corner-logos/takeout.png";

// 로고가 아직 없는 코너는 이 맵에 없으면 자동으로 텍스트 폴백 — 나중에
// 로고가 추가되면 이 맵에 한 줄만 더하면 된다(다른 코드 변경 불필요).
const CORNER_LOGOS: Record<string, string> = {
  "고슬고슬비빈": gosleulgosleulbibin,
  "도담찌개": dodamjjigae,
  "한식사계": hansiksagye,
  "동방식객": dongbangsikgaek,
  "모던키친": moderncuisine,
  "싱푸차이나": xingfuchina,
  "Take Out": takeout,
};

// 로고 원본이 진한 잉크색(검정/갈색 등) 텍스트를 포함해 다크모드 표면색과
// 대비가 떨어질 수 있어, 테마 무관하게 항상 밝은 배경의 작은 배지 안에
// 그린다 — 로고 PNG 자체의 색은 못 바꾸니 배경을 고정하는 쪽으로 대응.
export function CornerLogo({
  cornerName,
  height = 18,
}: {
  cornerName: string;
  height?: number;
}) {
  const src = CORNER_LOGOS[cornerName];
  if (!src) return <>{cornerName}</>;
  return (
    <span
      className="inline-flex items-center rounded px-1.5 py-0.5"
      style={{ background: "#ffffff", border: "1px solid var(--border)" }}
      title={cornerName}
    >
      <img src={src} alt={cornerName} style={{ height, width: "auto", display: "block" }} />
    </span>
  );
}
