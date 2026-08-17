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

// §105: 로고가 눈에 잘 안 띈다는 신고(2026-08) — 흰 배지가 흰 카드/표
// 배경 위에서 거의 안 보였고(테두리도 --border의 옅은 회색이라 대비가
// 약함), 필터 버튼·SegmentedControl처럼 이미 자체 테두리가 있는 곳에
// 얹으면 상자 안에 또 상자가 생겨 되레 로고가 더 작아 보였다. 그래서:
// - 배지 자체를 키우고(기본 20px) 테두리를 고정 rgba로 진하게, 그림자를
//   추가해 배경과 무관하게 항상 도드라지게 했다.
// - 이미 테두리가 있는 컨테이너 안에서 쓰는 곳은 `bare`로 배지를 없애고
//   이미지만 키워서 넣는다(이중 상자 방지).
export function CornerLogo({
  cornerName,
  height = 20,
  bare = false,
}: {
  cornerName: string;
  height?: number;
  /** 이미 자체 테두리/배경이 있는 버튼·SegmentedControl 안에서 쓸 때 —
   * 배지(흰 배경+테두리+그림자)를 없애고 로고 이미지만 그린다. */
  bare?: boolean;
}) {
  const src = CORNER_LOGOS[cornerName];
  if (!src) return <>{cornerName}</>;
  const img = <img src={src} alt={cornerName} style={{ height, width: "auto", display: "block" }} />;
  if (bare) {
    return (
      <span className="inline-flex items-center" title={cornerName}>
        {img}
      </span>
    );
  }
  return (
    <span
      className="inline-flex items-center rounded-md px-2 py-1"
      style={{
        background: "#ffffff",
        border: "1.5px solid rgba(15, 23, 32, 0.16)",
        boxShadow: "0 1px 3px rgba(15, 23, 32, 0.12)",
      }}
      title={cornerName}
    >
      {img}
    </span>
  );
}
