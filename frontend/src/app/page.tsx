import { HeatwaveApp } from '@/components/HeatwaveApp'

// A server component: it renders the page shell, and HeatwaveApp (a client
// component) takes over in the browser for all the interactivity.
export default function Home() {
  return <HeatwaveApp />
}
