import { useState } from "react";
import { Loader2, Rocket } from "lucide-react";
import ToneChipSelector from "./ToneChipSelector";
import PlatformSelector from "./PlatformSelector";
import AssetUploadZone from "./AssetUploadZone";
import VoiceBriefRecorder from "./VoiceBriefRecorder";

export default function BriefForm({ onSubmit, loading }) {
  const [brandName, setBrandName] = useState("");
  const [productDescription, setProductDescription] = useState("");
  const [targetAudience, setTargetAudience] = useState("");
  const [campaignGoal, setCampaignGoal] = useState("");
  const [toneKeywords, setToneKeywords] = useState([]);
  const [platforms, setPlatforms] = useState([]);
  const [files, setFiles] = useState([]);
  const [voiceBlob, setVoiceBlob] = useState(null);

  const canSubmit =
    brandName.trim() && productDescription.trim() && platforms.length > 0;

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!canSubmit || loading) return;
    onSubmit({
      brand_name: brandName,
      product_description: productDescription,
      target_audience: targetAudience,
      campaign_goal: campaignGoal,
      tone_keywords: toneKeywords,
      platforms,
      files,
      voiceBlob,
    });
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6 max-w-2xl mx-auto">
      {/* Brand Name */}
      <div>
        <label htmlFor="brand-name" className="block text-sm font-medium mb-1.5">
          Brand Name *
        </label>
        <input
          id="brand-name"
          type="text"
          value={brandName}
          onChange={(e) => setBrandName(e.target.value)}
          placeholder="e.g. Patagonia, Glossier, Tesla"
          required
          className="w-full px-4 py-3 bg-brand-surface border border-brand-border rounded-xl text-white placeholder-brand-muted/50 focus:outline-none focus:border-brand-accent transition-colors"
        />
      </div>

      {/* Product Description */}
      <div>
        <label htmlFor="product-desc" className="block text-sm font-medium mb-1.5">
          Product / Service Description *
        </label>
        <textarea
          id="product-desc"
          value={productDescription}
          onChange={(e) => setProductDescription(e.target.value)}
          placeholder="Describe what you're marketing..."
          required
          rows={3}
          className="w-full px-4 py-3 bg-brand-surface border border-brand-border rounded-xl text-white placeholder-brand-muted/50 focus:outline-none focus:border-brand-accent transition-colors resize-none"
        />
      </div>

      {/* Target Audience */}
      <div>
        <label htmlFor="audience" className="block text-sm font-medium mb-1.5">
          Target Audience
        </label>
        <input
          id="audience"
          type="text"
          value={targetAudience}
          onChange={(e) => setTargetAudience(e.target.value)}
          placeholder="e.g. Eco-conscious millennials aged 25-35"
          className="w-full px-4 py-3 bg-brand-surface border border-brand-border rounded-xl text-white placeholder-brand-muted/50 focus:outline-none focus:border-brand-accent transition-colors"
        />
      </div>

      {/* Campaign Goal */}
      <div>
        <label htmlFor="goal" className="block text-sm font-medium mb-1.5">
          Campaign Goal
        </label>
        <input
          id="goal"
          type="text"
          value={campaignGoal}
          onChange={(e) => setCampaignGoal(e.target.value)}
          placeholder="e.g. Product launch, brand awareness, seasonal push"
          className="w-full px-4 py-3 bg-brand-surface border border-brand-border rounded-xl text-white placeholder-brand-muted/50 focus:outline-none focus:border-brand-accent transition-colors"
        />
      </div>

      {/* Tone Keywords */}
      <div>
        <label className="block text-sm font-medium mb-2">Tone Keywords</label>
        <ToneChipSelector selected={toneKeywords} onChange={setToneKeywords} />
      </div>

      {/* Platforms */}
      <div>
        <label className="block text-sm font-medium mb-2">
          Platforms * <span className="text-brand-muted font-normal">(select at least 1)</span>
        </label>
        <PlatformSelector selected={platforms} onChange={setPlatforms} />
      </div>

      {/* Asset Upload */}
      <div>
        <label className="block text-sm font-medium mb-2">Brand Assets</label>
        <AssetUploadZone files={files} onChange={setFiles} />
      </div>

      {/* Voice Brief */}
      <div>
        <label className="block text-sm font-medium mb-2">Voice Brief</label>
        <VoiceBriefRecorder
          onComplete={(blob) => setVoiceBlob(blob)}
        />
      </div>

      {/* Submit */}
      <button
        type="submit"
        disabled={!canSubmit || loading}
        className={`w-full flex items-center justify-center gap-2 px-6 py-4 rounded-xl font-semibold text-base transition-all duration-300
          ${
            canSubmit && !loading
              ? "bg-brand-accent hover:bg-brand-accent-hover text-white shadow-lg shadow-brand-accent/25 hover:shadow-brand-accent/40"
              : "bg-brand-border text-brand-muted cursor-not-allowed"
          }`}
      >
        {loading ? (
          <>
            <Loader2 size={18} className="animate-spin" />
            Launching Campaign...
          </>
        ) : (
          <>
            <Rocket size={18} />
            Launch Campaign
          </>
        )}
      </button>
    </form>
  );
}
