import { Routes, Route } from "react-router-dom";
import IntakePage from "./pages/IntakePage";
import CanvasPage from "./pages/CanvasPage";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<IntakePage />} />
      <Route path="/canvas/:campaignId" element={<CanvasPage />} />
    </Routes>
  );
}
