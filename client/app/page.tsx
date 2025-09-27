'use client'

import { useChat } from 'ai/react'
import { useState, useEffect } from 'react'
import { Send, Database, Filter, X, Eye, EyeOff } from 'lucide-react'
import { cn } from '@/lib/utils'
import ProposalTable from '@/components/ProposalTable'
import Filters from '@/components/Filters'
import { Proposal } from '@/lib/dataUtils'

export default function Home() {
  const [showSqlDrawer, setShowSqlDrawer] = useState(false)
  const [currentSql, setCurrentSql] = useState('')
  const [messageProposals, setMessageProposals] = useState<Record<string, Proposal[]>>({})
  const [messageFilteredProposals, setMessageFilteredProposals] = useState<Record<string, Proposal[]>>({})
  const [messageDescriptions, setMessageDescriptions] = useState<Record<string, Record<string, string>>>({})
  const [messageTextPortions, setMessageTextPortions] = useState<Record<string, string>>({})
  const [showSql, setShowSql] = useState(false)
  const [count, setCount] = useState<number | null>(null)
  const [isLoadingProposals, setIsLoadingProposals] = useState(false)
  const [currentFilteredMessageId, setCurrentFilteredMessageId] = useState<string | null>(null)
  const [filters, setFilters] = useState({
    network: 'all',
    type: 'all',
    dateRange: 'all'
  })
  const [isBackendReady, setIsBackendReady] = useState(false)
  const [isCheckingBackend, setIsCheckingBackend] = useState(true)
  const [retryCount, setRetryCount] = useState(0)

  // Example messages
  const exampleMessages = [
    "Find Kusama proposals",
    "What treasury proposals exist?",
    "Tell me about clarys proposal"
  ]

  const handleExampleClick = (message: string) => {
    if (input.trim()) return // Don't override existing input
    handleInputChange({ target: { value: message } } as any)
  }

  // Health check function
  const checkBackendHealth = async () => {
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/v1/healthz`)
      if (response.ok) {
        setIsBackendReady(true)
        setIsCheckingBackend(false)
      } else {
        // Retry after 2 seconds if backend is not ready (max 15 retries = 30 seconds)
        if (retryCount < 15) {
          setRetryCount(prev => prev + 1)
          setTimeout(checkBackendHealth, 2000)
        } else {
          // After 30 seconds, show error but allow user to try anyway
          setIsCheckingBackend(false)
          setIsBackendReady(true) // Allow user to try
        }
      }
    } catch (error) {
      console.log('Backend not ready, retrying...', error)
      // Retry after 2 seconds if there's an error (max 15 retries = 30 seconds)
      if (retryCount < 15) {
        setRetryCount(prev => prev + 1)
        setTimeout(checkBackendHealth, 2000)
      } else {
        // After 30 seconds, show error but allow user to try anyway
        setIsCheckingBackend(false)
        setIsBackendReady(true) // Allow user to try
      }
    }
  }

  // Check backend health on component mount
  useEffect(() => {
    checkBackendHealth()
  }, [])

  const { messages, input, handleInputChange, handleSubmit, isLoading } = useChat({
    api: '/api/chat',
    body: {
      filters: filters
    },
    onFinish: (message) => {
      console.log('Message finished:', message)
      setIsLoadingProposals(false)
      // The data will be handled by the useEffect below
    },
    onError: (error) => {
      console.error('Chat error:', error)
      setIsLoadingProposals(false)
    }
  })

  // Handle data extraction from the last message using useEffect
  useEffect(() => {
    const lastMessage = messages[messages.length - 1]
    if (lastMessage && lastMessage.role === 'assistant' && lastMessage.content) {
      const content = lastMessage.content
      console.log('Checking content for proposal data:', content)

      // Check for proposal descriptions data (JSON format)
      try {
        const jsonMatch = content.match(/\{.*"type":\s*"proposal_descriptions".*\}/)
        if (jsonMatch) {
          const data = JSON.parse(jsonMatch[0])
          console.log('Extracted proposal descriptions:', data)

          if (data.type === 'proposal_descriptions' && data.proposals) {
            const descriptions: Record<string, string> = {}
            data.proposals.forEach((proposal: any) => {
              if (proposal.id && proposal.description) {
                descriptions[proposal.id] = proposal.description
              }
            })
            setMessageDescriptions(prev => ({ ...prev, [lastMessage.id]: descriptions }))
          }
        }
      } catch (e) {
        console.log('No proposal descriptions found in content or parsing error:', e)
      }

      // Check for regular proposal data (array format) - look for the proposals array
      try {
        // Look for proposals array in the content - more flexible regex
        const proposalsMatch = content.match(/\[{.*"id":\s*"[^"]+".*}\]/)
        if (proposalsMatch) {
          const jsonData = JSON.parse(proposalsMatch[0])
          console.log('Extracted proposals array:', jsonData)

          if (Array.isArray(jsonData) && jsonData.length > 0 && jsonData[0].id) {
            console.log('Setting proposals from content array:', jsonData)
            // Removed - now handled per message
            setCount(jsonData.length)
            return
          }
        }

        // Also look for "Data: " prefix
        const dataMatch = content.match(/Data: (\[{.*}\])/)
        if (dataMatch) {
          const jsonData = JSON.parse(dataMatch[1])
          console.log('Extracted data from Data prefix:', jsonData)

          if (Array.isArray(jsonData)) {
            console.log('Setting proposals from Data prefix:', jsonData)
            // Removed - now handled per message
            setCount(jsonData.length)
          }
        }

        // Look for any JSON array that looks like proposals
        const anyJsonMatch = content.match(/\[{.*"id".*}\]/)
        if (anyJsonMatch) {
          const jsonData = JSON.parse(anyJsonMatch[0])
          console.log('Extracted any JSON array:', jsonData)

          if (Array.isArray(jsonData) && jsonData.length > 0 && jsonData[0].id) {
            console.log('Setting proposals from any JSON array:', jsonData)
            // Removed - now handled per message
            setCount(jsonData.length)
          }
        }

        // Try to find any JSON array in the content
        const lines = content.split('\n')
        for (const line of lines) {
          if (line.trim().startsWith('[') && line.trim().endsWith(']')) {
            try {
              const jsonData = JSON.parse(line.trim())
              if (Array.isArray(jsonData) && jsonData.length > 0 && jsonData[0].id) {
                console.log('Setting proposals from line array:', jsonData)
                // Removed - now handled per message
                setCount(jsonData.length)
                break
              }
            } catch (e) {
              // Continue to next line
            }
          }
        }
      } catch (e) {
        console.log('No JSON found in content or parsing error:', e)
      }
    }
  }, [messages]) // Only run when messages change

  // Handle streaming data extraction from the chat API
  useEffect(() => {
    const lastMessage = messages[messages.length - 1]
    if (lastMessage && lastMessage.role === 'assistant' && lastMessage.content) {
      const content = lastMessage.content

      // Look for proposals data that comes from streaming
      try {
        // Check if content contains proposal data in the format we expect
        if (content.includes('Found') && (content.includes('proposals') || content.includes('relevant proposals'))) {
          // Split content into text portion and examples
          const firstProposalIndex = content.indexOf('## Proposal 1:')
          let textPortion = ''
          let examplesContent = content
          
          if (firstProposalIndex > 0) {
            textPortion = content.substring(0, firstProposalIndex).trim()
            examplesContent = content.substring(firstProposalIndex)
            
            // Store the text portion for display
            setMessageTextPortions(prev => ({ ...prev, [lastMessage.id]: textPortion }))
          }
          
          // Extract proposals from the markdown content
          const proposalMatches = examplesContent.match(/## Proposal \d+: ([^\n]+)\n\*\*ID:\*\* ([^\n]+)\n\*\*Type:\*\* ([^\n]+)\n\*\*Network:\*\* ([^\n]+)\n\*\*Proposer:\*\* ([^\n]+)\n\*\*Status:\*\* ([^\n]+)\n\*\*Created:\*\* ([^\n]+)(?:\n\*\*Amount:\*\* ([^\n]+))?(?:\n\*\*Description:\*\* ([^\n]+))?/g)

          if (proposalMatches) {
            const extractedProposals = proposalMatches.map((match, index) => {
              const lines = match.split('\n')
              const title = lines[0].replace(/## Proposal \d+: /, '')
              const id = lines[1].replace(/\*\*ID:\*\* /, '')
              const type = lines[2].replace(/\*\*Type:\*\* /, '')
              const network = lines[3].replace(/\*\*Network:\*\* /, '')
              const proposer = lines[4].replace(/\*\*Proposer:\*\* /, '')
              const status = lines[5].replace(/\*\*Status:\*\* /, '')
              const created = lines[6].replace(/\*\*Created:\*\* /, '')
              
              // Extract amount and description if present
              let amount = null
              let description = '[Loading description...]'
              
              for (let i = 7; i < lines.length; i++) {
                if (lines[i].startsWith('**Amount:**')) {
                  amount = lines[i].replace(/\*\*Amount:\*\* /, '')
                } else if (lines[i].startsWith('**Description:**')) {
                  description = lines[i].replace(/\*\*Description:\*\* /, '')
                }
              }

              return {
                id,
                title,
                type,
                network,
                proposer,
                status,
                created_at: created,
                amount_numeric: amount ? parseFloat(amount) : undefined,
                currency: amount ? 'DOT' : undefined,
                description
              }
            })

            console.log('Extracted proposals from markdown:', extractedProposals)
            setMessageProposals(prev => ({ ...prev, [lastMessage.id]: extractedProposals }))
            setMessageFilteredProposals(prev => ({ ...prev, [lastMessage.id]: extractedProposals }))
            setCurrentFilteredMessageId(lastMessage.id)
            setCount(extractedProposals.length)
            setIsLoadingProposals(false)
          }
        }
      } catch (e) {
        console.log('Error extracting proposals from markdown:', e)
      }
    }
  }, [messages])

  // Force table display when we have proposals data
  useEffect(() => {
    if (Object.keys(messageProposals).length > 0) {
      console.log('Message proposals found, forcing table display:', messageProposals)
    }
  }, [messageProposals])

  // Filter proposals based on current filters
  const filterProposals = (proposalList: Proposal[], currentFilters: any) => {
    return proposalList.filter(proposal => {
      // Network filter
      if (currentFilters.network !== 'all' && proposal.network?.toLowerCase() !== currentFilters.network) {
        return false
      }

      // Type filter
      if (currentFilters.type !== 'all' && proposal.type !== currentFilters.type) {
        return false
      }

      // Date range filter
      if (currentFilters.dateRange !== 'all' && proposal.created_at) {
        const proposalDate = new Date(proposal.created_at)
        const now = new Date()
        const daysDiff = Math.floor((now.getTime() - proposalDate.getTime()) / (1000 * 60 * 60 * 24))

        switch (currentFilters.dateRange) {
          case '1d':
            if (daysDiff > 1) return false
            break
          case '7d':
            if (daysDiff > 7) return false
            break
          case '30d':
            if (daysDiff > 30) return false
            break
          case '90d':
            if (daysDiff > 90) return false
            break
          case '1y':
            if (daysDiff > 365) return false
            break
        }
      }

      return true
    })
  }

  // Handle filter application
  const handleApplyFilters = (newFilters: any) => {
    setFilters(newFilters)

    // Apply filters to the current filtered message or the most recent message with proposals
    const targetMessageId = currentFilteredMessageId || (messages.length > 0 ? messages[messages.length - 1].id : null)
    if (targetMessageId && messageProposals[targetMessageId]) {
      const filtered = filterProposals(messageProposals[targetMessageId], newFilters)
      setMessageFilteredProposals(prev => ({ ...prev, [targetMessageId]: filtered }))
    }
  }

  // Debug: Log current state
  useEffect(() => {
    console.log('Current message proposals:', messageProposals)
    console.log('Current message descriptions:', messageDescriptions)
    console.log('Current count:', count)
  }, [messageProposals, messageDescriptions, count])

  // Debug: Log messages changes (only when they actually change)
  useEffect(() => {
    console.log('Current messages:', messages)
    console.log('Current message proposals:', messageProposals)
    console.log('Current message descriptions:', messageDescriptions)
    console.log('Current count:', count)
  }, [messages, messageProposals, messageDescriptions, count])

  // Check if message contains count-related keywords
  const isCountQuery = (message: string) => {
    return /count|how many|total|number of/i.test(message)
  }

  return (
    <div className="flex h-screen bg-slate-50">
      {/* Backend Loading Overlay */}
      {isCheckingBackend && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-8 max-w-md mx-4 text-center">
            <div className="flex flex-col items-center space-y-4">
              <div className="flex space-x-2">
                <div className="w-3 h-3 bg-blue-500 rounded-full animate-bounce"></div>
                <div className="w-3 h-3 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }}></div>
                <div className="w-3 h-3 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
              </div>
              <div>
                <h3 className="text-lg font-semibold text-slate-900 mb-2">Loading System</h3>
                <p className="text-slate-600 text-sm">Please wait while we prepare the data explorer...</p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col">
        {/* Header */}
        <div className="bg-white border-b border-slate-200 px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
                <Database className="w-5 h-5 text-white" />
              </div>
              <div>
                <h1 className="text-xl font-semibold text-slate-900">
                  Onchain Explorer
                </h1>
                <p className="text-slate-500 text-sm">Ask questions about onchain data</p>
              </div>
            </div>
            
          </div>
        </div>

        {/* Example Messages */}
        {messages.length === 0 && (
          <div className="px-6 py-8">
            <div className="max-w-2xl mx-auto">
              <h2 className="text-lg font-medium text-slate-900 mb-4">Try asking:</h2>
              <div className="grid gap-3">
                {exampleMessages.map((message, index) => (
                  <button
                    key={index}
                    onClick={() => isBackendReady && handleExampleClick(message)}
                    disabled={!isBackendReady}
                    className={`text-left p-4 border rounded-lg transition-all duration-200 group ${
                      isBackendReady
                        ? 'bg-white border-slate-200 hover:border-blue-300 hover:bg-blue-50'
                        : 'bg-slate-100 border-slate-200 cursor-not-allowed'
                    }`}
                  >
                    <div className="flex items-center space-x-3">
                      <div className={`w-2 h-2 rounded-full ${
                        isBackendReady 
                          ? 'bg-blue-500 group-hover:bg-blue-600' 
                          : 'bg-slate-300'
                      }`}></div>
                      <span className={`font-medium ${
                        isBackendReady 
                          ? 'text-slate-700 group-hover:text-blue-700' 
                          : 'text-slate-400'
                      }`}>{message}</span>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-6">
          {messages.map((message, index) => {
            // Get proposals for this specific message
            const messageProposalsData = messageProposals[message.id] || []
            const messageDescriptionsData = messageDescriptions[message.id] || {}

            // Use filtered data if this is the current filtered message, otherwise use original data
            const messageFilteredProposalsData = currentFilteredMessageId === message.id
              ? (messageFilteredProposals[message.id] || messageProposalsData)
              : messageProposalsData

            // Check if this message contains proposals and should show table instead
            const shouldShowTable = message.role === 'assistant' &&
              messageProposalsData.length > 0 &&
              (message.content.includes('Found') && (message.content.includes('proposals') || message.content.includes('relevant proposals')))
            
            // For count queries, we should show the table even if there's text content
            const isCountQueryMessage = isCountQuery(message.content)

            // Show loader if we're loading proposals for the last message only
            const isLastMessage = index === messages.length - 1
            if (isLoadingProposals && isLastMessage && message.role === 'assistant' && message.content.includes('Found')) {
              return (
                <div key={message.id} className="space-y-4">
                  <div className="flex justify-start">
                    <div className="bg-white border border-slate-200 rounded-lg px-4 py-3 max-w-4xl">
                      <div className="flex items-center space-x-3">
                        <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce"></div>
                        <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }}></div>
                        <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
                        <span className="text-slate-600 text-sm">Loading proposals...</span>
                      </div>
                    </div>
                  </div>
                </div>
              )
            }

            if (shouldShowTable) {
              return (
                <div key={message.id} className="space-y-4 w-full">
                  {/* Show text portion for count queries or other cases */}
                  {messageTextPortions[message.id] && (
                    <div className='flex items-center space-x-2'>
                      <div className="flex justify-start">
                        <div className="bg-white border border-slate-200 rounded-lg px-4 py-3 max-w-4xl">
                          <div className="prose prose-sm max-w-none">
                            <p className="whitespace-pre-wrap break-words leading-relaxed text-black">
                              {messageTextPortions[message.id]}
                            </p>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                  
                  <div className="mb-4 mt-4">
                      <span className="inline-flex items-center px-3 py-1.5 rounded-full text-sm font-semibold bg-blue-100 text-blue-800 border border-blue-200">
                        📊 {messageFilteredProposalsData.length} results found
                        {messageFilteredProposalsData.length !== messageProposalsData.length && (
                          <span className="ml-2 text-blue-600">
                            (filtered from {messageProposalsData.length})
                          </span>
                        )}
                      </span>
                    </div>
                 
                  
                  {/* Show the table */}
                  <div className="w-full">
                    {messageFilteredProposalsData.length > 0 ? (
                      <ProposalTable
                        proposals={messageFilteredProposalsData}
                        proposalDescriptions={messageDescriptionsData}
                      />
                    ) : (
                      <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-8 text-center">
                        <div className="text-slate-500 text-lg font-medium mb-2">No proposals found</div>
                        <div className="text-slate-400 text-sm">Try adjusting your filters to see more results</div>
                      </div>
                    )}
                  </div>
                </div>
              )
            }

            return (
              <div
                key={message.id}
                className={cn(
                  'flex',
                  message.role === 'user' ? 'justify-end' : 'justify-start'
                )}
              >
                <div
                  className={cn(
                    'max-w-[85%] rounded-lg px-4 py-3 ',
                    message.role === 'user'
                      ? 'bg-blue-600 text-white'
                      : 'bg-white border border-slate-200 text-slate-900'
                  )}
                >
                  <div className="prose prose-sm max-w-none">
                    {/* Show text portion if it exists, otherwise show full content */}
                    {messageTextPortions[message.id] ? (
                      <div>
                        <p className="whitespace-pre-wrap break-words leading-relaxed mb-4">
                          {messageTextPortions[message.id]}
                        </p>
                        {/* The table will be shown below via the ProposalTable component */}
                      </div>
                    ) : (
                      <p className="whitespace-pre-wrap break-words leading-relaxed">{message.content}</p>
                    )}
                  </div>

                  {/* Count pill for count queries - only show if we don't have proposals data to show in table */}
                  {message.role === 'assistant' && count !== null && isCountQuery(message.content) && messageProposalsData.length === 0 && (
                    <div className="mt-3">
                      <span className="inline-flex items-center px-3 py-1.5 rounded-full text-xs font-semibold bg-blue-100 text-blue-800 border border-blue-200">
                        📊 {count} results found
                      </span>
                    </div>
                  )}

                  {/* SQL toggle for SQL queries */}
                  {message.role === 'assistant' && showSql && currentSql && (
                    <div className="mt-3 flex items-center space-x-2">
                      <button
                        onClick={() => setShowSqlDrawer(!showSqlDrawer)}
                        className="inline-flex items-center px-4 py-2 border border-slate-300 shadow-sm text-xs font-medium rounded-lg text-slate-700 bg-white hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-colors"
                      >
                        {showSqlDrawer ? <EyeOff className="w-3 h-3 mr-2" /> : <Eye className="w-3 h-3 mr-2" />}
                        {showSqlDrawer ? 'Hide SQL' : 'Show SQL'}
                      </button>
                    </div>
                  )}
                </div>
              </div>
            )
          })}

          {isLoading && (
            <div className="flex justify-start">
              <div className="bg-white border border-slate-200 rounded-lg px-4 py-3">
                <div className="flex space-x-2">
                  <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce"></div>
                  <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }}></div>
                  <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Input Form */}
        <div className="bg-white border-t border-slate-200 px-6 py-4">
          <form onSubmit={(e) => {
            e.preventDefault()
            if (input.trim() && isBackendReady) {
              // Reset count and set loading state
              setCount(null)
              setIsLoadingProposals(true)
              handleSubmit(e)
            }
          }} className="flex space-x-3">
            <div className="flex-1 relative">
              <input
                value={input}
                onChange={handleInputChange}
                placeholder={isBackendReady ? "Ask about onchain data..." : "Loading... Please wait"}
                disabled={!isBackendReady}
                className={`w-full border rounded-lg px-4 py-3 pr-12 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-slate-900 placeholder-slate-500 ${
                  isBackendReady 
                    ? 'border-slate-300 bg-white' 
                    : 'border-slate-200 bg-slate-100 cursor-not-allowed'
                }`}
              />
              <div className="absolute right-3 top-1/2 transform -translate-y-1/2">
                <Send className={`w-4 h-4 ${isBackendReady ? 'text-slate-400' : 'text-slate-300'}`} />
              </div>
            </div>
            <button
              type="submit"
              disabled={isLoading || !input.trim() || !isBackendReady}
              className="bg-blue-600 text-white px-6 py-3 rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2 transition-colors"
            >
              <span className="font-medium">Send</span>
            </button>
          </form>
        </div>
      </div>

      {/* Right Sidebar - Only Filters */}
      <div className="w-80 bg-white border-l border-slate-200 flex flex-col">
        {/* Filters */}
        <div className="p-6">
          <div className="flex flex-col space-x-2 mb-6">

            <div className='flex items-center space-x-2'> <Filter className="w-5 h-5 text-slate-600" /> <h3 className="text-lg font-semibold text-slate-900">Filters</h3>
             </div>
             <h3 className="text-sm text-slate-900">Only work on the most recent message</h3>
          </div>
          <Filters onApplyFilters={handleApplyFilters} />
        </div>
      </div>

      {/* SQL Drawer */}
      {showSqlDrawer && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[80vh] flex flex-col">
            <div className="flex items-center justify-between p-6 border-b border-slate-200">
              <div className="flex items-center space-x-3">
                <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
                  <Database className="w-5 h-5 text-white" />
                </div>
                <h3 className="text-lg font-semibold text-slate-900">Generated SQL</h3>
              </div>
              <button
                onClick={() => setShowSqlDrawer(false)}
                className="text-slate-400 hover:text-slate-600 p-2 rounded-lg hover:bg-slate-100 transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="flex-1 p-6 overflow-auto">
              <pre className="bg-slate-50 p-4 rounded-lg text-sm overflow-x-auto border border-slate-200">
                <code className="text-slate-800">{currentSql}</code>
              </pre>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
