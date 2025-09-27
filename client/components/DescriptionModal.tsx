'use client'

import { X, ExternalLink } from 'lucide-react'
import { cleanText } from '@/lib/dataUtils'

interface DescriptionModalProps {
  isOpen: boolean
  onClose: () => void
  proposal: {
    id?: number | string
    title?: string
    description?: string
    network?: string
    type?: string
    proposer?: string
    status?: string
    created_at?: string
    [key: string]: any
  }
}

// Helper function to format description text for better readability
const formatDescription = (text: string) => {
  if (!text) return ''
  
  return text
    // Fix encoded spaces and special characters
    .replace(/x20/g, ' ')
    .replace(/&#x20;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    
    // Fix broken URLs
    .replace(/httpsdocs\.google\.com/g, 'https://docs.google.com')
    .replace(/httpsforms\.gle/g, 'https://forms.gle')
    .replace(/httpst\.co/g, 'https://t.co')
    .replace(/httpsdrive\.google\.com/g, 'https://drive.google.com')
    .replace(/httpsdocs\.google\.com/g, 'https://docs.google.com')
    
    // Fix markdown formatting
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>') // Bold text
    .replace(/\*(.*?)\*/g, '<em>$1</em>') // Italic text
    
    // Fix bullet points and lists
    .replace(/\* (.*?)(?=\n|$)/g, '<li>$1</li>')
    .replace(/\d+\. (.*?)(?=\n|$)/g, '<li>$1</li>')
    
    // Create proper paragraphs
    .replace(/\n\n+/g, '</p><p>')
    .replace(/\n/g, '<br>')
    
    // Wrap in paragraphs
    .replace(/^/, '<p>')
    .replace(/$/, '</p>')
    
    // Clean up spacing
    .replace(/\s+/g, ' ')
    .replace(/\s*<br>\s*/g, '<br>')
    .replace(/\s*<\/p>\s*<p>\s*/g, '</p><p>')
    
    // Fix broken links and make them clickable
    .replace(/(https?:\/\/[^\s]+)/g, '<a href="$1" target="_blank" rel="noopener noreferrer" class="text-blue-600 hover:text-blue-800 underline">$1</a>')
}

export default function DescriptionModal({ isOpen, onClose, proposal }: DescriptionModalProps) {
  if (!isOpen) return null

  const cleanedDescription = cleanText(proposal.description)
  
  // Generate external links
  const getExternalLinks = () => {
    const network = proposal.network?.toLowerCase() || 'polkadot'
    const id = proposal.id
    const type = proposal.type?.toLowerCase() || 'referendum'
    
    if (!id) return null

    const baseUrls = {
      polkadot: {
        polkassembly: 'https://polkadot.polkassembly.io',
        subsquare: 'https://polkadot.subsquare.io',
        subscan: 'https://polkadot.subscan.io'
      },
      kusama: {
        polkassembly: 'https://kusama.polkassembly.io',
        subsquare: 'https://kusama.subsquare.io',
        subscan: 'https://kusama.subscan.io'
      }
    }

    const urls = baseUrls[network as keyof typeof baseUrls] || baseUrls.polkadot

    // Determine the correct path based on proposal type
    let path = '/referenda'
    if (type.includes('treasury')) {
      path = '/treasury'
    } else if (type.includes('council')) {
      path = '/council'
    } else if (type.includes('tip')) {
      path = '/tips'
    } else if (type.includes('bounty')) {
      path = '/bounties'
    }

    return {
      polkassembly: `${urls.polkassembly}${path}/${id}`,
      subsquare: `${urls.subsquare}${path}/${id}`,
      subscan: `${urls.subscan}${path}/${id}`
    }
  }

  const links = getExternalLinks()

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-4xl max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-slate-200">
          <div className="flex items-center space-x-3">
            <div className="w-8 h-8 bg-gradient-to-r from-blue-600 to-purple-600 rounded-lg flex items-center justify-center">
              <ExternalLink className="w-5 h-5 text-white" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-slate-900">
                Proposal Details
              </h3>
              <p className="text-sm text-slate-600">ID: {proposal.id || 'N/A'}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-600 p-2 rounded-lg hover:bg-slate-100 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto p-6">
          <div className="space-y-6">
            {/* Proposal Info */}
            <div className="space-y-4">
              {/* Main Info Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="text-sm font-medium text-slate-600">Title</label>
                  <p className="text-slate-900 font-medium">{proposal.title || 'Untitled'}</p>
                </div>
                <div>
                  <label className="text-sm font-medium text-slate-600">Type</label>
                  <p className="text-slate-900">{proposal.type || 'Unknown'}</p>
                </div>
                <div>
                  <label className="text-sm font-medium text-slate-600">Network</label>
                  <p className="text-slate-900">{proposal.network || 'Unknown'}</p>
                </div>
                <div>
                  <label className="text-sm font-medium text-slate-600">Proposer</label>
                  <p className="text-slate-900 font-mono text-sm break-all">{proposal.proposer || 'Unknown'}</p>
                </div>
              </div>
              
              {/* Status and Created - Side by Side */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="text-sm font-medium text-slate-600">Status</label>
                  <div className={`flex flex-col w-[200px] items-center px-3 py-1 rounded-full text-sm font-medium ${
                    proposal.status === 'Passed' ? 'bg-green-100 text-green-800' :
                    proposal.status === 'Failed' ? 'bg-red-100 text-red-800' :
                    proposal.status === 'Active' ? 'bg-yellow-100 text-yellow-800' :
                    proposal.status === 'Deciding' ? 'bg-blue-100 text-blue-800' :
                    proposal.status === 'Rejected' ? 'bg-red-100 text-red-800' :
                    'bg-gray-100 text-gray-800'
                  }`}>
                    {proposal.status || 'Unknown'}
                  </div>
                </div>
                <div>
                  <label className="text-sm font-medium text-slate-600">Created</label>
                  <p className="text-slate-900">{proposal.created_at ? new Date(proposal.created_at).toLocaleDateString() : 'Unknown'}</p>
                </div>
              </div>
            </div>

            {/* Description */}
            <div>
              <label className="text-sm font-medium text-slate-600 mb-2 block">Description</label>
              <div className="bg-slate-50 p-4 rounded-lg border border-slate-200 max-h-96 overflow-y-auto">
                <div 
                  className="text-slate-900 leading-relaxed prose prose-sm max-w-none"
                  dangerouslySetInnerHTML={{ 
                    __html: formatDescription(cleanedDescription) || 'No description available' 
                  }}
                />
              </div>
            </div>

            {/* External Links */}
            {links && (
              <div>
                <label className="text-sm font-medium text-slate-600 mb-2 block">External Links</label>
                <div className="flex space-x-3">
                  <a
                    href={links.polkassembly}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center px-4 py-2 rounded-lg text-sm font-medium bg-blue-100 text-blue-800 hover:bg-blue-200 transition-colors"
                  >
                    <ExternalLink className="w-4 h-4 mr-2" />
                    Polkassembly
                  </a>
                  <a
                    href={links.subsquare}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center px-4 py-2 rounded-lg text-sm font-medium bg-green-100 text-green-800 hover:bg-green-200 transition-colors"
                  >
                    <ExternalLink className="w-4 h-4 mr-2" />
                    Subsquare
                  </a>
                  <a
                    href={links.subscan}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center px-4 py-2 rounded-lg text-sm font-medium bg-purple-100 text-purple-800 hover:bg-purple-200 transition-colors"
                  >
                    <ExternalLink className="w-4 h-4 mr-2" />
                    Subscan
                  </a>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="p-6 border-t border-slate-200">
          <button
            onClick={onClose}
            className="w-full bg-gradient-to-r from-blue-600 to-blue-700 text-white px-6 py-3 rounded-xl hover:from-blue-700 hover:to-blue-800 transition-all duration-200"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
