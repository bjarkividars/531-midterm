import { Transcription } from './components/Transcription'
import { FileUpload } from './components/FileUpload'
import './App.css'

function App() {
  return (
    <div className="app">
      <FileUpload />
      <Transcription />
    </div>
  )
}

export default App
