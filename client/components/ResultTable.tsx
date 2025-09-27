import { Database, Eye, ExternalLink } from "lucide-react"
import { useState } from "react"
import { Proposal, cleanText, getFirstLine, formatAmount, formatDate, formatProposalType } from "@/lib/dataUtils"
import DescriptionModal from "./DescriptionModal"

interface ResultTableProps {
  results: Proposal[]
}

// Helper function to generate external links
const getExternalLinks = (result: Proposal) => {
  const network = result.network?.toLowerCase() || 'polkadot'
  const id = result.id
  
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

export default function ResultTable({ results }: ResultTableProps) {
  const [selectedProposal, setSelectedProposal] = useState<Proposal | null>(null)
  const [isModalOpen, setIsModalOpen] = useState(false)

  if (!results || results.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center py-8 text-slate-500">
        <div className="w-16 h-16 bg-slate-100 rounded-full flex items-center justify-center mb-4">
          <Database className="w-8 h-8 text-slate-400" />
        </div>
        <p className="text-slate-600 font-medium">No results to display</p>
        <p className="text-sm text-slate-500 mt-1">Ask a question to see results here</p>
      </div>
    )
  }

  const handleViewDescription = (proposal: Proposal) => {
    setSelectedProposal(proposal)
    setIsModalOpen(true)
  }

  const handleCloseModal = () => {
    setIsModalOpen(false)
    setSelectedProposal(null)
  }

  return (
    <>
      <div className="h-full flex flex-col">
        <div className="flex-1 overflow-auto">
          <div className="min-w-full">
            <table className="min-w-full divide-y divide-slate-200">
              <thead className="bg-slate-50 sticky top-0 z-10">
                <tr>
                  <th className="px-3 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                    ID
                  </th>
                  <th className="px-3 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                    Title
                  </th>
                  <th className="px-3 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                    Type
                  </th>
                  <th className="px-3 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                    Network
                  </th>
                  <th className="px-3 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                    Amount
                  </th>
                  <th className="px-3 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                    Status
                  </th>
                  <th className="px-3 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                    Description
                  </th>
                  <th className="px-3 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-slate-200">
                {results.map((result, index) => {
                  const links = getExternalLinks(result)
                  
                  return (
                    <tr key={result.id || index} className="hover:bg-slate-50 transition-colors">
                      {/* ID */}
                      <td className="px-3 py-3 text-sm text-slate-900 font-mono">
                        {result.id || '-'}
                      </td>
                      
                      {/* Title */}
                      <td className="px-3 py-3 text-sm text-slate-900 max-w-xs">
                        <div className="truncate font-medium" title={cleanText(result.title)}>
                          {cleanText(result.title) || 'Untitled'}
                        </div>
                      </td>
                      
                      {/* Type */}
                      <td className="px-3 py-3 text-sm text-slate-900">
                        <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                          {formatProposalType(result.type)}
                        </span>
                      </td>
                      
                      {/* Network */}
                      <td className="px-3 py-3 text-sm text-slate-900">
                        <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800">
                          {result.network || '-'}
                        </span>
                      </td>
                      
                      {/* Amount */}
                      <td className="px-3 py-3 text-sm text-slate-900">
                        {formatAmount(result.amount_numeric, result.currency)}
                      </td>
                      
                      {/* Status */}
                      <td className="px-3 py-3 text-sm text-slate-900">
                        <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${
                          result.status === 'Passed' ? 'bg-green-100 text-green-800' :
                          result.status === 'Failed' ? 'bg-red-100 text-red-800' :
                          result.status === 'Active' ? 'bg-yellow-100 text-yellow-800' :
                          'bg-gray-100 text-gray-800'
                        }`}>
                          {result.status || '-'}
                        </span>
                      </td>
                      
                      {/* Description */}
                      <td className="px-3 py-3 text-sm text-slate-900 max-w-xs">
                        <div className="truncate" title={cleanText(result.description)}>
                          {getFirstLine(result.description)}
                        </div>
                      </td>
                      
                      {/* Actions */}
                      <td className="px-3 py-3 text-sm text-slate-900">
                        <div className="flex space-x-2">
                          <button
                            onClick={() => handleViewDescription(result)}
                            className="inline-flex items-center px-3 py-1 rounded text-xs font-medium bg-blue-100 text-blue-800 hover:bg-blue-200 transition-colors"
                            title="View full description"
                          >
                            <Eye className="w-3 h-3 mr-1" />
                            View
                          </button>
                          
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
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Description Modal */}
      {selectedProposal && (
        <DescriptionModal
          isOpen={isModalOpen}
          onClose={handleCloseModal}
          proposal={selectedProposal}
        />
      )}
    </>
  )
}
