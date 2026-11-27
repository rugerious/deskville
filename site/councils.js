// What changes between the councils' sites: presentation only. Which data a
// resident sees comes from their token, never from this file or the address (D33, D46).
// Facts here come from content/<council>/*.md. To use a painting or photo instead of the
// illustration, put it in site/art/ and change `art` (and `artCredit`).
export const COUNCILS = {
  wigan: {
    name: "Wigan",
    site: "https://www.wigan.gov.uk/",
    ink: "#1f3d36", soft: "#e4ebe6",
    art: "art/wigan.jpg",
    artAlt: "Trencherfield Mill and its chimney above the Leeds and Liverpool Canal at Wigan Pier, with a narrowboat moored in front",
    artTitle: "The canal at Wigan Pier",
    artText: "The Leeds and Liverpool Canal, the Pier warehouses and Trencherfield Mill.",
    artCredit: "Image made for Deskville.",
    putOut: "Bins out by 6am on collection day.",
    binsSource: "https://www.wigan.gov.uk/Resident/Bins-Recycling/Which-bin-do-I-use.aspx",
    bins: [
      { colour: "Black", hex: "#2a2d30", takes: "General waste", every: "every 3 weeks" },
      { colour: "Brown", hex: "#7b5434", takes: "Cans, glass, plastics, cartons", every: "every 3 weeks" },
      { colour: "Blue", hex: "#2d67b0", takes: "Paper and card", every: "every 3 weeks" },
      { colour: "Green", hex: "#3e7e3b", takes: "Food and garden waste", every: "every 2 weeks" },
    ],
    skyline: `<path d="M0 58 H40 V40 L52 32 L64 40 V58 H74 V30 H150 V58 H160 V8 H168 V58 H176 V36 H230 V58"/>
      <path d="M84 38 h8 v6 h-8z M100 38 h8 v6 h-8z M116 38 h8 v6 h-8z M132 38 h8 v6 h-8z M84 48 h8 v6 h-8z M100 48 h8 v6 h-8z M116 48 h8 v6 h-8z M132 48 h8 v6 h-8z"/>
      <path d="M186 44 h7 v6 h-7z M200 44 h7 v6 h-7z M214 44 h7 v6 h-7z M48 46 v12 M56 46 v12"/>
      <path d="M230 58 Q262 28 294 58 M240 50 v8 M284 50 v8 M248 44 v14 M276 44 v14 M262 40 v18"/>
      <path d="M294 58 H330 V46 L338 40 L346 46 V58 H380"/>
      <path d="M0 64 H380 M20 70 H80 M150 70 H260"/>`,
    request: "What's happening with WGN-26-006985?",
  },
  bury: {
    name: "Bury",
    site: "https://www.bury.gov.uk/",
    ink: "#1d3557", soft: "#e2e8f0",
    art: "art/bury.jpg", artPosition: "right center",
    artAlt: "Holcombe Hill with Peel Tower on its summit, above the rooftops of the valley",
    artTitle: "Holcombe Hill from Bury",
    artText: "Peel Tower on Holcombe Hill, above the valley.",
    artCredit: "Image made for Deskville.",
    putOut: "Bins out by 7am on collection day.",
    binsSource: "https://www.bury.gov.uk/waste-and-recycling/bin-collection-days-and-alerts",
    bins: [
      { colour: "Grey", hex: "#8c9398", takes: "General waste", every: "every 3 weeks" },
      { colour: "Green", hex: "#3e7e3b", takes: "Paper and card", every: "every 3 weeks" },
      { colour: "Blue", hex: "#2d67b0", takes: "Cans, glass, plastics", every: "every 3 weeks" },
      { colour: "Brown", hex: "#7b5434", takes: "Garden and food waste", every: "every 2 weeks" },
    ],
    skyline: `<path d="M0 58 C40 52 70 40 110 30 C140 22 170 20 200 24 C230 28 260 40 290 46 C320 52 350 56 380 58"/>
      <path d="M150 21 V6 H162 V21 M148 6 H164 M150 6 V2 M156 6 V2 M162 6 V2"/>
      <path d="M20 58 V48 L28 42 L36 48 V58 M44 58 V46 L54 40 L64 46 V58 M72 58 V50 L80 44 L88 50 V58"/>
      <path d="M300 58 V40 H310 V58 M305 40 L305 22 M300 40 L305 22 L310 40 M318 58 V48 H350 V58 M326 52 h5 v6 M338 52 h5 v6"/>
      <path d="M0 64 H380 M40 70 H120 M220 70 H330"/>`,
    request: "Any news on BRY/2026/07376?",
  },
};

// The questions behind the service shortcuts: the same for both councils, answered
// from each council's own pages.
export const SERVICES = [
  { id: "bins", title: "Bins and recycling", text: "Collection days, missed bins, bulky items.", ask: "My bin was missed. When can I report it?" },
  { id: "tax", title: "Council tax", text: "Paying, bands and discounts.", ask: "I live alone. Can I get money off my council tax?" },
  { id: "roads", title: "Roads and parking", text: "Permits, fines and potholes.", ask: "How do I report a pothole?" },
  { id: "requests", title: "My requests", text: "Where a request you made has got to.", ask: null },
];

export function councilForHost(host) {
  const first = host.split(".")[0];
  if (COUNCILS[first]) return first;
  const asked = new URLSearchParams(location.search).get("council"); // local preview only
  return COUNCILS[asked] ? asked : "wigan";
}
