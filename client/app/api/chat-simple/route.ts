// Simple fallback API route that doesn't use streaming
const BASE_API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export async function POST(req: Request) {
  const { messages, filters } = await req.json()
  const lastMessage = messages[messages.length - 1]

  try {
    // Forward the query to our server's non-streaming endpoint
    const response = await fetch(`${BASE_API_URL}/api/v1/query`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        query: lastMessage.content,
        filters: filters || {}
      }),
    })

    if (!response.ok) {
      throw new Error('Failed to process query')
    }

    const data = await response.json()
    console.log('Backend response:', data)

    // Return a simple response
    return Response.json({
      message: data.response || 'No response received',
      data: {
        results: data.results || [],
        count: data.count || 0,
        sql: data.sql_query || null,
        show_sql: !!data.sql_query
      }
    })

  } catch (error) {
    console.error('API error:', error)
    return Response.json({
      message: 'Error processing your request',
      data: {
        results: [],
        count: 0,
        sql: null,
        show_sql: false
      }
    }, { status: 500 })
  }
}
