import { initializeApp } from "firebase/app";
import {
  getFirestore,
  doc,
  collection,
  onSnapshot,
  setDoc,
  updateDoc,
  query,
  where,
} from "firebase/firestore";
import { getAuth, signInAnonymously } from "firebase/auth";

const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID || "brandforge-489114",
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
};

const app = initializeApp(firebaseConfig);
const db = getFirestore(app);
const auth = getAuth(app);

export async function ensureAuth() {
  if (!auth.currentUser) {
    await signInAnonymously(auth);
  }
  return auth.currentUser;
}

export function subscribeToCampaign(campaignId, callback) {
  return onSnapshot(doc(db, "campaigns", campaignId), (snap) => {
    if (snap.exists()) callback(snap.data());
  });
}

export function subscribeToBrandDNA(campaignId, callback) {
  const q = query(
    collection(db, "brand_dna"),
    where("campaign_id", "==", campaignId),
  );
  return onSnapshot(q, (snap) => {
    if (!snap.empty) {
      // Sort client-side to avoid requiring a Firestore composite index
      const docs = snap.docs.map((d) => d.data());
      docs.sort((a, b) => (b.version || 0) - (a.version || 0));
      callback(docs[0]);
    }
  });
}

export function subscribeToAgentRuns(campaignId, callback) {
  return onSnapshot(
    collection(db, "campaigns", campaignId, "agent_runs"),
    (snap) => {
      const runs = {};
      snap.forEach((d) => {
        const data = d.data();
        runs[data.agent_name] = data;
      });
      callback(runs);
    },
  );
}

export function subscribeToImages(campaignId, callback) {
  const q = query(
    collection(db, "generated_images"),
    where("campaign_id", "==", campaignId),
  );
  return onSnapshot(q, (snap) => {
    callback(snap.docs.map((d) => ({ id: d.id, ...d.data() })));
  });
}

export function subscribeToVideos(campaignId, callback) {
  const q = query(
    collection(db, "generated_videos"),
    where("campaign_id", "==", campaignId),
  );
  return onSnapshot(q, (snap) => {
    callback(snap.docs.map((d) => ({ id: d.id, ...d.data() })));
  });
}

export function subscribeToQAResults(campaignId, callback) {
  const q = query(
    collection(db, "qa_results"),
    where("campaign_id", "==", campaignId),
  );
  return onSnapshot(q, (snap) => {
    callback(snap.docs.map((d) => ({ id: d.id, ...d.data() })));
  });
}

export function subscribeToQASummary(campaignId, callback) {
  return onSnapshot(doc(db, "qa_summaries", campaignId), (snap) => {
    if (snap.exists()) callback(snap.data());
  });
}

export { db, auth };
