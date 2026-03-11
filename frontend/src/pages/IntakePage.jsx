import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Sparkles } from "lucide-react";
import BriefForm from "../components/intake/BriefForm";
import useCampaignStore from "../stores/campaignStore";
import { ensureAuth } from "../lib/firestore";
import { uploadAsset, uploadVoiceBrief } from "../lib/storage";

export default function IntakePage() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const navigate = useNavigate();
  const initCampaign = useCampaignStore((s) => s.initCampaign);

  const handleSubmit = async (formData) => {
    setLoading(true);
    setError(null);

    try {
      await ensureAuth();

      const brief = {
        brand_name: formData.brand_name,
        product_description: formData.product_description,
        target_audience: formData.target_audience || "",
        campaign_goal: formData.campaign_goal || "",
        tone_keywords: formData.tone_keywords,
        platforms: formData.platforms,
        uploaded_asset_urls: [],
        voice_brief_url: null,
      };

      const campaignId = await initCampaign(brief);

      // Upload assets in background
      if (formData.files?.length > 0) {
        for (const file of formData.files) {
          try {
            await uploadAsset(file, campaignId);
          } catch (e) {
            console.error("Asset upload failed:", e);
          }
        }
      }

      // Upload voice brief in background
      if (formData.voiceBlob) {
        try {
          await uploadVoiceBrief(formData.voiceBlob, campaignId);
        } catch (e) {
          console.error("Voice upload failed:", e);
        }
      }

      navigate(`/canvas/${campaignId}`);
    } catch (e) {
      setError(e.message || "Failed to create campaign");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="py-6 px-6 border-b border-brand-border">
        <div className="flex items-center gap-2">
          <Sparkles size={20} className="text-brand-accent" />
          <span className="font-display font-bold text-lg">BrandForge</span>
        </div>
      </header>

      {/* Hero + Form */}
      <main className="flex-1 py-12 px-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="text-center mb-10"
        >
          <h1 className="text-4xl md:text-5xl font-display font-extrabold mb-3 bg-gradient-to-r from-white via-brand-accent to-white bg-clip-text text-transparent">
            Your AI Creative Director.
          </h1>
          <p className="text-brand-muted text-lg max-w-xl mx-auto">
            Describe your brand. Watch an AI-powered team build your entire
            marketing campaign in real time.
          </p>
        </motion.div>

        {error && (
          <div className="max-w-2xl mx-auto mb-6 p-4 bg-brand-danger/10 border border-brand-danger/30 rounded-xl text-sm text-brand-danger">
            {error}
          </div>
        )}

        <BriefForm onSubmit={handleSubmit} loading={loading} />
      </main>

      {/* Footer */}
      <footer className="py-4 px-6 border-t border-brand-border text-center text-xs text-brand-muted">
        Built with Google ADK + Gemini
      </footer>
    </div>
  );
}
