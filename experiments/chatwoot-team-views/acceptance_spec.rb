# Maintainer-owned request checks; run on an isolated test database.
require 'rails_helper'

RSpec.describe 'Team views public requirements', type: :request do
  let(:account) { create(:account) }
  let(:alice) { create(:user, account: account, role: :agent) }
  let(:bob) { create(:user, account: account, role: :agent) }
  let(:admin) { create(:user, account: account, role: :administrator) }
  let(:outsider) { create(:user, account: account, role: :agent) }
  let(:team) { create(:team, account: account) }
  let(:query) { { 'payload' => [{ 'attribute_key' => 'status', 'filter_operator' => 'equal_to', 'values' => ['open'], 'query_operator' => nil }] } }
  let(:path) { "/api/v1/accounts/#{account.id}/custom_filters" }
  let(:alice_headers) { alice.create_new_auth_token }
  let(:bob_headers) { bob.create_new_auth_token }
  let(:admin_headers) { admin.create_new_auth_token }
  let(:view_id) do
    team.add_members([alice.id, bob.id])
    post path, headers: alice_headers, params: { custom_filter: { name: 'Team open', query: query, filter_type: 'conversation', team_id: team.id } }, as: :json
    expect(response).to have_http_status(:success)
    response.parsed_body.fetch('id')
  end

  it 'keeps shared views after creator deletion, even with a loaded association' do
    id = view_id
    alice.custom_filters.load
    perform_enqueued_jobs(only: ActiveRecord::DestroyAssociationAsyncJob) { alice.destroy! }
    get "#{path}/#{id}", headers: bob_headers
    expect(response).to have_http_status(:success)
    expect(response.parsed_body['team_id']).to eq(team.id)
    patch "#{path}/#{id}", headers: admin_headers, params: { custom_filter: { name: 'Maintained' } }, as: :json
    expect(response).to have_http_status(:success)
    expect(response.parsed_body['name']).to eq('Maintained')
  end

  it 'retains shared views after account removal and the account cleanup job' do
    id = view_id
    alice.account_users.find_by!(account: account).destroy!
    Agents::DestroyJob.perform_now(account, alice)
    get "#{path}/#{id}", headers: alice_headers
    expect(response.status).to be_in([401, 403, 404])
    get "#{path}/#{id}", headers: bob_headers
    expect(response).to have_http_status(:success)
    patch "#{path}/#{id}", headers: admin_headers, params: { custom_filter: { name: 'Retained' } }, as: :json
    expect(response).to have_http_status(:success)
  end

  it 'uses fresh membership within an existing login session, including creator rejoining' do
    id = view_id
    get "#{path}/#{id}", headers: alice_headers
    expect(response).to have_http_status(:success)
    team.remove_members([alice.id])
    get "#{path}/#{id}", headers: alice_headers
    expect(response).to have_http_status(:not_found)
    patch "#{path}/#{id}", headers: alice_headers, params: { custom_filter: { name: 'Denied' } }, as: :json
    expect(response).to have_http_status(:not_found)
    get "#{path}/#{id}", headers: bob_headers
    expect(response.parsed_body['name']).to eq('Team open')
    team.add_members([alice.id])
    patch "#{path}/#{id}", headers: alice_headers, params: { custom_filter: { name: 'Rejoined' } }, as: :json
    expect(response).to have_http_status(:success)
  end

  it 'allows newly added members and revokes removed members immediately' do
    id = view_id
    headers = outsider.create_new_auth_token
    get "#{path}/#{id}", headers: headers
    expect(response).to have_http_status(:not_found)
    team.add_members([outsider.id])
    get "#{path}/#{id}", headers: headers
    expect(response).to have_http_status(:success)
    team.remove_members([outsider.id])
    get path, headers: headers
    expect(response.parsed_body.map { |row| row['id'] }).not_to include(id)
  end

  it 'does not expose deleted teams or disturb personal and unrelated shared views' do
    id = view_id
    personal = create(:custom_filter, account: account, user: bob)
    other_team = create(:team, account: account)
    post path, headers: admin_headers, params: { custom_filter: { name: 'Other', query: query, filter_type: 'conversation', team_id: other_team.id } }, as: :json
    other_id = response.parsed_body.fetch('id')
    team.destroy!
    get "#{path}/#{id}", headers: admin_headers
    expect(response).to have_http_status(:not_found)
    get "#{path}/#{personal.id}", headers: bob_headers
    expect(response).to have_http_status(:success)
    get "#{path}/#{other_id}", headers: admin_headers
    expect(response).to have_http_status(:success)
  end

  it 'allows administrator creation without membership and avoids duplicate lists' do
    id = view_id
    get path, headers: admin_headers
    expect(response.parsed_body.count { |row| row['id'] == id }).to eq(1)
    team.add_members([admin.id])
    get path, headers: admin_headers
    expect(response.parsed_body.count { |row| row['id'] == id }).to eq(1)
  end

  it 'does not grant administrators access to personal filters' do
    personal = create(:custom_filter, account: account, user: alice)
    get "#{path}/#{personal.id}", headers: admin_headers
    expect(response).to have_http_status(:not_found)
    get path, headers: admin_headers
    expect(response.parsed_body.map { |row| row['id'] }).not_to include(personal.id)
  end

  it 'does not let a reader delete the view' do
    id = view_id
    delete "#{path}/#{id}", headers: bob_headers
    expect(response).to have_http_status(:forbidden)
    get "#{path}/#{id}", headers: alice_headers
    expect(response).to have_http_status(:success)
    delete "#{path}/#{id}", headers: admin_headers
    expect(response).to have_http_status(:no_content)
    get "#{path}/#{id}", headers: alice_headers
    expect(response).to have_http_status(:not_found)
  end

  it 'rejects invalid shared query shapes without creating a record' do
    team.add_members([alice.id])
    [nil, {}, { payload: [] }, { payload: [{ attribute_key: 'nonexistent', filter_operator: 'equal_to', values: ['x'] }] }].each do |invalid_query|
      expect do
        post path, headers: alice_headers, params: { custom_filter: { name: 'Invalid', filter_type: 'conversation', team_id: team.id, query: invalid_query } }, as: :json
      end.not_to change(CustomFilter, :count)
      expect(response).to have_http_status(:unprocessable_entity)
    end
  end

  it 'does not let the caller forge ownership or change audience' do
    id = view_id
    patch "#{path}/#{id}", headers: alice_headers,
          params: { custom_filter: { user_id: bob.id, account_id: create(:account).id } }, as: :json
    expect(response).to have_http_status(:success)
    patch "#{path}/#{id}", headers: bob_headers, params: { custom_filter: { name: 'Forged' } }, as: :json
    expect(response).to have_http_status(:forbidden)
    patch "#{path}/#{id}", headers: alice_headers, params: { custom_filter: { team_id: team.id } }, as: :json
    expect(response).to have_http_status(:success)
    patch "#{path}/#{id}", headers: alice_headers, params: { custom_filter: { team_id: nil } }, as: :json
    expect(response).to have_http_status(:unprocessable_entity)
  end

  it 'keeps unread badges viewer-specific after warming caches and revoking permissions' do
    id = view_id
    account.enable_features!(:conversation_unread_counts, :unread_count_for_filters)
    general = create(:inbox, account: account)
    restricted = create(:inbox, account: account)
    [alice, bob].each { |user| create(:inbox_member, inbox: general, user: user) }
    create(:inbox_member, inbox: restricted, user: alice)
    create_unread_conversation(account: account, inbox: general)
    hidden = create_unread_conversation(account: account, inbox: restricted)
    unread_path = "/api/v1/accounts/#{account.id}/conversations/unread_counts"
    [alice_headers, bob_headers, alice_headers, bob_headers].zip([2, 1, 2, 1]).each do |headers, expected|
      get unread_path, headers: headers
      expect(response).to have_http_status(:success)
      expect(response.parsed_body.dig('payload', 'folders', id.to_s)).to eq(expected)
    end
    get "/api/v1/accounts/#{account.id}/conversations/#{hidden.display_id}", headers: bob_headers
    expect(response.status).to be_in([401, 403, 404])
    team.remove_members([bob.id])
    get unread_path, headers: bob_headers
    expect(response.parsed_body.dig('payload', 'folders')).not_to have_key(id.to_s)
    team.add_members([bob.id])
    InboxMember.find_by!(inbox: general, user: bob).destroy!
    get unread_path, headers: bob_headers
    expect(response.parsed_body.dig('payload', 'folders')).not_to have_key(id.to_s)
    get "#{path}/#{id}", headers: bob_headers
    expect(response).to have_http_status(:success)
    post "/api/v1/accounts/#{account.id}/conversations/filter", headers: bob_headers, params: response.parsed_body['query'], as: :json
    expect(response.parsed_body['payload']).to be_empty
    expect(response.parsed_body.dig('meta', 'all_count')).to eq(0)
  end

  it 'preserves AND/OR conditions and paginates only authorized conversations' do
    id = view_id
    general = create(:inbox, account: account)
    hidden = create(:inbox, account: account)
    create(:inbox_member, inbox: general, user: bob)
    visible = create_list(:conversation, 26, account: account, inbox: general, status: :open)
    create(:conversation, account: account, inbox: general, status: :resolved)
    create(:conversation, account: account, inbox: hidden, status: :open)
    combined = { payload: [
      { attribute_key: 'status', filter_operator: 'equal_to', values: ['open'], query_operator: 'AND' },
      { attribute_key: 'inbox_id', filter_operator: 'equal_to', values: [general.id], query_operator: nil }
    ] }
    patch "#{path}/#{id}", headers: alice_headers, params: { custom_filter: { query: combined } }, as: :json
    expect(response).to have_http_status(:success)
    get "#{path}/#{id}", headers: bob_headers
    stored = response.parsed_body['query']
    expect(stored).to eq(combined.deep_stringify_keys)
    found = []
    (1..5).each do |page|
      post "/api/v1/accounts/#{account.id}/conversations/filter", headers: bob_headers, params: stored.merge('page' => page), as: :json
      expect(response).to have_http_status(:success)
      expect(response.parsed_body.dig('meta', 'all_count')).to eq(26)
      rows = response.parsed_body['payload']
      break if rows.empty?

      found.concat(rows.pluck('id'))
    end
    expect(found).to match_array(visible.map { |conversation| conversation.reload.display_id })
    combined[:payload][0][:query_operator] = 'OR'
    combined[:payload][1] = { attribute_key: 'status', filter_operator: 'equal_to', values: ['resolved'], query_operator: nil }
    patch "#{path}/#{id}", headers: alice_headers, params: { custom_filter: { query: combined } }, as: :json
    expect(response).to have_http_status(:success)
    post "/api/v1/accounts/#{account.id}/conversations/filter", headers: bob_headers, params: combined, as: :json
    expect(response.parsed_body.dig('meta', 'all_count')).to eq(27)
  end

end
