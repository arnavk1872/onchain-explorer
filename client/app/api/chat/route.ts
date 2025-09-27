import { StreamingTextResponse } from 'ai'

const BASE_API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export async function POST(req: Request) {
  const { messages, filters } = await req.json()
  const lastMessage = messages[messages.length - 1]

  try {
    // Forward the query to our server's streaming endpoint
    const response = await fetch(`${BASE_API_URL}/api/v1/query/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        query: lastMessage.content,
        user_id: 'frontend'
      }),
    })

    if (!response.ok) {
      throw new Error('Failed to process query')
    }

    // Handle streaming response
    const encoder = new TextEncoder()
    const stream = new ReadableStream({
      async start(controller) {
        const reader = response.body?.getReader()
        if (!reader) {
          controller.close()
          return
        }

        let buffer = ''
        let proposalsData: any[] = []
        let descriptionsData: any[] = []

        try {
          while (true) {
            const { done, value } = await reader.read()
            if (done) break

            buffer += new TextDecoder().decode(value)
            const lines = buffer.split('\n')
            buffer = lines.pop() || ''

            for (const line of lines) {
              if (line.trim().startsWith('data: ')) {
                try {
                  const data = JSON.parse(line.slice(6))
                  
                  if (data.stage === 'final_answer') {
                    // Stream the main response text
                    const responseText = data.payload.answer || 'No response received'
                    const words = responseText.split(' ')
                    
                    for (const word of words) {
                      controller.enqueue(encoder.encode(word + ' '))
                      await new Promise(resolve => setTimeout(resolve, 50))
                    }
                  } else if (data.stage === 'proposals_data') {
                    proposalsData = data.payload.proposals || []
                  } else if (data.stage === 'proposal_descriptions') {
                    descriptionsData = data.payload.proposals || []
                  }
                } catch (e) {
                  // Ignore parsing errors for non-JSON lines
                }
              }
            }
          }

          // Send proposals data
          if (proposalsData.length > 0) {
            controller.enqueue(encoder.encode('\n\n' + JSON.stringify(proposalsData)))
          }

          // Send descriptions data
          if (descriptionsData.length > 0) {
            const descriptions = {
              type: 'proposal_descriptions',
              proposals: descriptionsData.map((proposal: any) => ({
                id: proposal.id,
                description: proposal.description || 'No description available'
              }))
            }
            controller.enqueue(encoder.encode('\n\n' + JSON.stringify(descriptions)))
          }

        } catch (error) {
          console.error('Streaming error:', error)
        } finally {
          controller.close()
        }
      },
    })

    // Return the streaming response with data
    return new StreamingTextResponse(stream, {
      headers: {
        'Content-Type': 'text/plain; charset=utf-8',
      },
    })

  } catch (error) {
    console.error('API error:', error)
    
    // Return error response
    const encoder = new TextEncoder()
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode('❌ Error processing your request'))
        controller.close()
      },
    })

    return new StreamingTextResponse(stream, {
      status: 500,
    })
  }
}
