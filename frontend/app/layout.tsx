import { DataVisionAssistantRoot } from '../components/assistant/DataVisionAssistantRoot';
import './globals.css';

export const metadata = { title: 'DataVision AI', description: 'Data Intelligence Workspace' };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="fr"><body>{children}<DataVisionAssistantRoot /></body></html>;
}
