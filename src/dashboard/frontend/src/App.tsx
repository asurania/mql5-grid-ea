import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import SessionSchedule from '@/pages/SessionSchedule'
import GridPolicy from '@/pages/GridPolicy'
import RiskControls from '@/pages/RiskControls'
import LiveStatus from '@/pages/LiveStatus'

function App() {
  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <header className="border-b border-zinc-800 px-6 py-4">
        <h1 className="text-xl font-bold tracking-tight">ForexSlave Dashboard</h1>
        <p className="text-sm text-zinc-400">Trading system control panel</p>
      </header>
      <main className="mx-auto max-w-6xl p-6">
        <Tabs defaultValue="status" className="space-y-6">
          <TabsList className="bg-zinc-900">
            <TabsTrigger value="status">Live Status</TabsTrigger>
            <TabsTrigger value="sessions">Sessions</TabsTrigger>
            <TabsTrigger value="grid">Grid Policy</TabsTrigger>
            <TabsTrigger value="risk">Risk Controls</TabsTrigger>
          </TabsList>
          <TabsContent value="status"><LiveStatus /></TabsContent>
          <TabsContent value="sessions"><SessionSchedule /></TabsContent>
          <TabsContent value="grid"><GridPolicy /></TabsContent>
          <TabsContent value="risk"><RiskControls /></TabsContent>
        </Tabs>
      </main>
    </div>
  )
}

export default App