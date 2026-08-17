import gosleulgosleulbibin from "../assets/corner-logos/gosleulgosleulbibin.png";
import dodamjjigae from "../assets/corner-logos/dodamjjigae.png";
import hansiksagye from "../assets/corner-logos/hansiksagye.png";
import dongbangsikgaek from "../assets/corner-logos/dongbangsikgaek.png";
import moderncuisine from "../assets/corner-logos/moderncuisine.png";
import xingfuchina from "../assets/corner-logos/xingfuchina.png";
import takeout from "../assets/corner-logos/takeout.png";
import snapsnack from "../assets/corner-logos/snapsnack.png";

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
  "스냅스낵": snapsnack,
};

// §106: 흰 배경 배지에 가두지 말고 로고를 배경 없이 그대로 띄워달라는
// 요청(2026-08) — §105의 배지(흰 배경+테두리+그림자)를 걷어내고 이미지만
// 그린다.
export function CornerLogo({ cornerName, height = 20 }: { cornerName: string; height?: number }) {
  const src = CORNER_LOGOS[cornerName];
  if (!src) return <>{cornerName}</>;
  return (
    <span className="inline-flex items-center" title={cornerName}>
      <img src={src} alt={cornerName} style={{ height, width: "auto", display: "block" }} />
    </span>
  );
}
