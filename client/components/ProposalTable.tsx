import { useState } from "react"
import { Eye } from "lucide-react"
import { Proposal } from "@/lib/dataUtils"
import DescriptionModal from "./DescriptionModal"

interface ProposalTableProps {
  proposals: Proposal[]
  proposalDescriptions: Record<string, string>
}


// Helper function to clean text
const cleanText = (text: string | null | undefined): string => {
  if (!text) return ''
  return text.replace(/<[^>]*>/g, '').trim()
}

// Helper function to get first line of text
const getFirstLine = (text: string | null | undefined): string => {
  if (!text) return 'No description available'
  const cleaned = cleanText(text)
  return cleaned.split('\n')[0] || cleaned
}

// Helper function to format proposal type
const formatProposalType = (type: string | null | undefined): string => {
  if (!type) return 'Unknown'
  return type.replace(/([A-Z])/g, ' $1').trim()
}

// Helper function to format date
const formatDate = (dateString: string | null | undefined): string => {
  if (!dateString) return '-'
  try {
    return new Date(dateString).toLocaleDateString()
  } catch {
    return '-'
  }
}

export default function ProposalTable({ proposals, proposalDescriptions }: ProposalTableProps) {
  const [selectedProposal, setSelectedProposal] = useState<Proposal | null>(null)
  const [isModalOpen, setIsModalOpen] = useState(false)

  if (!proposals || proposals.length === 0) {
    return null
  }

  const handleViewDescription = (proposal: Proposal) => {
    const proposalWithDescription = {
      ...proposal,
      description: proposal.id ? proposalDescriptions[proposal.id] || proposal.description : proposal.description
    }
    setSelectedProposal(proposalWithDescription)
    setIsModalOpen(true)
  }

  const handleCloseModal = () => {
    setIsModalOpen(false)
    setSelectedProposal(null)
  }

  return (
    <>
      <div className="bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden max-w-full">
        <div className="overflow-x-auto max-w-full">
           <table className="w-full min-w-[600px] divide-y divide-slate-200">
            <thead className="bg-slate-50">
              <tr>
                <th className="px-3 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider w-32">
                  ID
                </th>
                <th className="px-3 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider w-64">
                  Title
                </th>
                <th className="px-3 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider w-24">
                  Type
                </th>
                <th className="px-3 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider w-20">
                  Network
                </th>
                 <th className="px-3 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider w-32">
                   Proposer
                 </th>
                 <th className="px-3 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider w-24">
                   Actions
                 </th>
              </tr>
            </thead>
             <tbody className="bg-white divide-y divide-slate-200">
               {proposals.map((proposal, index) => {
                
                return (
                  <tr key={proposal.id || index} className="hover:bg-slate-50 transition-colors">
                    {/* ID */}
                    <td className="px-3 py-3 text-sm text-slate-900 font-mono w-32">
                      <div className="truncate" title={proposal.id?.toString()}>
                        {proposal.id || '-'}
                      </div>
                    </td>
                    
                    {/* Title */}
                    <td className="px-3 py-3 text-sm text-slate-900 w-64">
                      <div className="truncate font-medium w-[300px] text-ellipsis" title={cleanText(proposal.title)}>
                        {cleanText(proposal.title) || 'Untitled'}
                      </div>
                    </td>
                    
                    {/* Type */}
                    <td className="px-3 py-3 text-sm text-slate-900 w-24">
                      <span className="inline-flex items-center whitespace-nowrap px-2 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                        {formatProposalType(proposal.type)}
                      </span>
                    </td>
                    
                    {/* Network */}
                    <td className="px-3 py-3 text-sm text-slate-900 w-20">
                      <span className="inline-flex items-center  px-2 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800">
                        {proposal.network || '-'}
                      </span>
                    </td>
                    
                     {/* Proposer */}
                     <td className="px-3 py-3 text-sm text-slate-900 w-32">
                       <div className="truncate font-mono text-xs" title={proposal.proposer}>
                         {proposal.proposer || '-'}
                       </div>
                     </td>
                     
                     {/* Actions */}
                     <td className="px-3 py-3 text-sm text-slate-900 w-24">
                       <button
                         onClick={() => handleViewDescription(proposal)}
                         className="inline-flex items-center px-3 py-1 rounded text-xs font-medium bg-blue-100 text-blue-800 hover:bg-blue-200 transition-colors"
                         title="View full description"
                       >
                         <Eye className="w-3 h-3 mr-1" />
                         View
                       </button>
                     </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
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
