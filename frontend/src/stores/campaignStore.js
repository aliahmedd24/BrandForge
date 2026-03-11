import { create } from "zustand";
import { createCampaign } from "../lib/api";
import {
  subscribeToCampaign,
  subscribeToBrandDNA,
  subscribeToAgentRuns,
  subscribeToImages,
  subscribeToVideos,
  subscribeToQAResults,
  subscribeToQASummary,
} from "../lib/firestore";

const AGENT_NAMES = [
  "brand_strategist",
  "scriptwriter",
  "mood_board_director",
  "image_generator",
  "video_producer",
  "copy_editor",
  "production_orchestrator",
  "brand_qa_inspector",
  "campaign_assembler",
  "qa_orchestrator",
  "brandforge_root",
];

const useCampaignStore = create((set, get) => ({
  campaignId: null,
  status: "idle",
  brandDNA: null,

  agentStatuses: Object.fromEntries(AGENT_NAMES.map((n) => [n, "idle"])),

  moodBoardImages: [],
  generatedImages: [],
  generatedVideos: [],
  copyPackage: null,
  scripts: [],

  qaResults: {},
  brandCoherenceScore: 0,

  activeAssetId: null,
  feedItems: [],
  assetBundle: null,

  _unsubs: [],

  setActiveAsset: (id) => set({ activeAssetId: id }),

  addFeedItem: (item) =>
    set((s) => ({
      feedItems: [
        ...s.feedItems,
        { ...item, id: item.id || crypto.randomUUID(), timestamp: Date.now() },
      ],
    })),

  initCampaign: async (brief) => {
    set({ status: "creating" });
    const data = await createCampaign(brief);
    set({ campaignId: data.campaign_id, status: "running" });
    get().subscribeToCampaign(data.campaign_id);
    return data.campaign_id;
  },

  subscribeToCampaign: (id) => {
    const unsubs = [];

    unsubs.push(
      subscribeToCampaign(id, (data) => {
        set({ status: data.status });
        if (data.asset_bundle_id) {
          set({ assetBundle: data.asset_bundle_id });
        }
      }),
    );

    unsubs.push(
      subscribeToBrandDNA(id, (dna) => {
        const prev = get().brandDNA;
        set({ brandDNA: dna });
        if (!prev) {
          get().addFeedItem({
            type: "brand_dna",
            agentName: "brand_strategist",
            payload: dna,
          });
        }
      }),
    );

    unsubs.push(
      subscribeToAgentRuns(id, (runs) => {
        const statuses = { ...get().agentStatuses };
        Object.entries(runs).forEach(([name, run]) => {
          statuses[name] = run.status;
        });
        set({ agentStatuses: statuses });
      }),
    );

    unsubs.push(
      subscribeToImages(id, (images) => {
        const prev = get().generatedImages;
        set({ generatedImages: images });
        const newImages = images.filter(
          (img) => !prev.find((p) => p.id === img.id),
        );
        newImages.forEach((img) => {
          get().addFeedItem({
            type: "image",
            agentName: "image_generator",
            payload: img,
          });
        });
      }),
    );

    unsubs.push(
      subscribeToVideos(id, (videos) => {
        const prev = get().generatedVideos;
        set({ generatedVideos: videos });
        const newVids = videos.filter(
          (v) => !prev.find((p) => p.id === v.id),
        );
        newVids.forEach((v) => {
          get().addFeedItem({
            type: "video",
            agentName: "video_producer",
            payload: v,
          });
        });
      }),
    );

    unsubs.push(
      subscribeToQAResults(id, (results) => {
        const map = {};
        results.forEach((r) => {
          map[r.asset_id] = r;
          if (r.status === "failed") {
            const existing = get().feedItems.find(
              (f) => f.type === "qa_violation" && f.payload?.asset_id === r.asset_id,
            );
            if (!existing) {
              get().addFeedItem({
                type: "qa_violation",
                agentName: "brand_qa_inspector",
                payload: r,
              });
            }
          }
        });
        set({ qaResults: map });
      }),
    );

    unsubs.push(
      subscribeToQASummary(id, (summary) => {
        set({ brandCoherenceScore: summary.brand_coherence_score * 100 });
      }),
    );

    set({ _unsubs: unsubs, campaignId: id });
  },

  cleanup: () => {
    get()._unsubs.forEach((fn) => fn());
    set({ _unsubs: [] });
  },
}));

export default useCampaignStore;
