import { useState, useEffect } from "react"
import { Eye, ExternalLink, Loader2 } from "lucide-react"
import { Proposal } from "@/lib/dataUtils"
import DescriptionModal from "./DescriptionModal"

interface ProposalCardProps {
  proposal: Proposal
  description?: string
  isLoading?: boolean
}

// Helper function to generate external links
const getExternalLinks = (proposal: Proposal) => {
  const network = proposal.network?.toLowerCase() || 'polkadot'
  const id = proposal.id
  
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

  return {
    polkassembly: `${urls.polkassembly}/proposal/${id}`,
    subsquare: `${urls.subsquare}/proposal/${id}`,
    subscan: `${urls.subscan}/proposal/${id}`
  }
}

export default function ProposalCard({ proposal, description, isLoading = false }: ProposalCardProps) {
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [proposalWithDescription, setProposalWithDescription] = useState<Proposal>(proposal)

  useEffect(() => {
    if (description) {
      setProposalWithDescription({
        ...proposal,
        description: description
      })
    }
  }, [description, proposal])

  const handleViewDescription = () => {
    setIsModalOpen(true)
  }

  const handleCloseModal = () => {
    setIsModalOpen(false)
  }

  const links = getExternalLinks(proposal)

  return (
    <>
      <div className="border border-slate-200 rounded-lg p-4 bg-white shadow-sm hover:shadow-md transition-shadow">
        <div className="flex justify-between items-start mb-3">
          <h3 className="text-lg font-semibold text-slate-900 line-clamp-2">
            {proposal.title || 'Untitled'}
          </h3>
          <div className="flex items-center space-x-2 ml-4">
            <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${
              proposal.status === 'Passed' ? 'bg-green-100 text-green-800' :
              proposal.status === 'Failed' ? 'bg-red-100 text-red-800' :
              proposal.status === 'Active' ? 'bg-yellow-100 text-yellow-800' :
              proposal.status === 'Deciding' ? 'bg-blue-100 text-blue-800' :
              'bg-gray-100 text-gray-800'
            }`}>
              {proposal.status || '-'}
            </span>
            <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
              {proposal.type || '-'}
            </span>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4 mb-4 text-sm">
          <div>
            <span className="text-slate-500">Network:</span>
            <span className="ml-2 font-medium">{proposal.network || '-'}</span>
          </div>
          <div>
            <span className="text-slate-500">Proposer:</span>
            <span className="ml-2 font-mono text-xs">{proposal.proposer || '-'}</span>
          </div>
          <div>
            <span className="text-slate-500">Created:</span>
            <span className="ml-2">{proposal.created_at ? new Date(proposal.created_at).toLocaleDateString() : '-'}</span>
          </div>
          <div>
            <span className="text-slate-500">ID:</span>
            <span className="ml-2 font-mono text-xs">{proposal.id || '-'}</span>
          </div>
        </div>

        <div className="mb-4">
          <span className="text-slate-500 text-sm">Description:</span>
          <div className="mt-1">
            {isLoading ? (
              <div className="flex items-center text-slate-500">
                <Loader2 className="w-4 h-4 animate-spin mr-2" />
                <span className="text-sm">Loading description...</span>
              </div>
            ) : description ? (
              <p className="text-sm text-slate-700 line-clamp-3">
                {description}
              </p>
            ) : (
              <p className="text-sm text-slate-500 italic">No description available</p>
            )}
          </div>
        </div>

        <div className="flex justify-between items-center">
          <div className="flex space-x-2">
            {description && (
              <button
                onClick={handleViewDescription}
                className="inline-flex items-center px-3 py-1 rounded text-xs font-medium bg-blue-100 text-blue-800 hover:bg-blue-200 transition-colors"
              >
                <Eye className="w-3 h-3 mr-1" />
                View Full Description
              </button>
            )}
          </div>

          {links && (
            <div className="flex space-x-1">
              <a
                href={links.polkassembly}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-purple-100 text-purple-800 hover:bg-purple-200 transition-colors"
                title="View on Polkassembly"
              >
                <ExternalLink className="w-3 h-3" />
              </a>
              <a
                href={links.subsquare}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-green-100 text-green-800 hover:bg-green-200 transition-colors"
                title="View on Subsquare"
              >
                <ExternalLink className="w-3 h-3" />
              </a>
              <a
                href={links.subscan}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-orange-100 text-orange-800 hover:bg-orange-200 transition-colors"
                title="View on Subscan"
              >
                <ExternalLink className="w-3 h-3" />
              </a>
            </div>
          )}
        </div>
      </div>

      {/* Description Modal */}
      {isModalOpen && (
        <DescriptionModal
          isOpen={isModalOpen}
          onClose={handleCloseModal}
          proposal={proposalWithDescription}
        />
      )}
    </>
  )
}
