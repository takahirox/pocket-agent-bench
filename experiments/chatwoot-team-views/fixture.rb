# Maintainer fixture: only the isolated qualification DB, never a shared database.
raise 'Unexpected database' unless ActiveRecord::Base.connection_db_config.database == 'pocket_team_views'
raise 'Expected empty accounts' unless Account.count.zero?

GlobalConfig.clear_cache
ConfigLoader.new.process
Time.zone = 'UTC'
result = { fixture_version: 1, accounts: {}, users: {}, teams: {}, inboxes: {}, conversations: [], personal: {} }
complete = ENV['POCKET_COMPLETE_FIXTURE'] == '1'
result[:fixture_version] = 2 if complete
query = { payload: [{ attribute_key: 'status', filter_operator: 'equal_to', values: ['open'], query_operator: nil }] }
ActiveRecord::Base.transaction do
  accounts = (complete ? %w[A B C] : %w[A B]).to_h { |key| [key, Account.create!(name: "Fixture #{key}", locale: 'en')] }
  accounts.each { |key, account| result[:accounts][key] = account.id }
  accounts.each_value { |account| account.enable_features!(:conversation_unread_counts, :unread_count_for_filters) } if complete
  users = {}
  keys = %w[admin alice bob carol dana erin foreign_admin]
  keys += %w[removed deleted pager page_admin] if complete
  keys.each do |key|
    account_key = if key == 'foreign_admin'
                    'B'
                  elsif %w[pager page_admin].include?(key)
                    'C'
                  else
                    'A'
                  end
    role = key.include?('admin') ? :administrator : :agent
    user = User.new(name: key, email: "#{key}@example.test", password: 'PocketBench123!')
    user.skip_confirmation!
    user.save!
    AccountUser.create!(account: accounts[account_key], user: user, role: role)
    users[key] = user
    result[:users][key] = { id: user.id, email: user.email, account: account_key, role: role }
  end
  AccountUser.create!(account: accounts['B'], user: users['removed'], role: :agent) if complete
  teams = {}
  team_rows = { 'support' => ['A', %w[alice bob dana]], 'billing' => ['A', %w[carol]],
               'support_b' => ['B', %w[foreign_admin]] }
  if complete
    team_rows['support'][1].concat(%w[removed deleted])
    team_rows['support_c'] = ['C', %w[pager]]
  end
  team_rows.each do |key, (account_key, members)|
    team = Team.create!(account: accounts[account_key], name: key, allow_auto_assign: false)
    team.add_members(members.map { |member| users.fetch(member).id })
    teams[key] = team
    result[:teams][key] = team.id
  end
  inbox_rows = { 'general' => ['A', %w[alice bob carol erin], 3, 1],
    'restricted' => ['A', %w[alice], 2, 1],
    'foreign' => ['B', %w[foreign_admin], 2, 0] }
  if complete
    inbox_rows['paging'] = ['C', %w[pager], 26, 1]
    inbox_rows['paging_hidden'] = ['C', %w[page_admin], 2, 0]
  end
  inbox_rows.each do |key, (account_key, members, open_count, resolved_count)|
    account = accounts.fetch(account_key)
    channel = Channel::WebWidget.create!(account: account, website_url: 'https://example.test')
    inbox = Inbox.create!(account: account, channel: channel, name: key)
    members.each { |member| InboxMember.create!(inbox: inbox, user: users.fetch(member)) }
    result[:inboxes][key] = inbox.id
    (open_count + resolved_count).times do |n|
      status = n < open_count ? 'open' : 'resolved'
      contact = Contact.create!(account: account, name: "#{key} customer #{n}", email: "#{key}-#{n}@example.test")
      ci = ContactInbox.create!(inbox: inbox, contact: contact, source_id: "#{key}-#{n}")
      assigned_team = if account_key == 'B'
                        teams['support_b']
                      elsif account_key == 'A' && n.odd?
                        teams['billing']
                      end
      conversation = Conversation.create!(account: account, inbox: inbox, contact: contact,
        contact_inbox: ci, status: status, team: assigned_team,
        assignee: n.even? ? users.fetch(members.first) : nil,
        agent_last_seen_at: Time.utc(2026, 1, 1), created_at: Time.utc(2026, 1, 2, 12) + n.hours)
      conversation.messages.create!(account: account, inbox: inbox, sender: contact, message_type: :incoming,
        content: "#{key} request #{n}", created_at: Time.utc(2026, 1, 2, 12) + n.hours)
      conversation.update!(status: status)
      conversation.reload # display_id is assigned by a PostgreSQL trigger
      result[:conversations] << { id: conversation.id, display_id: conversation.display_id,
        account: account_key, inbox: key, status: status, assignee_id: conversation.assignee_id }
    end
  end
  %w[alice bob].each do |key|
    filter = CustomFilter.create!(account: accounts['A'], user: users[key], name: 'My open requests',
      filter_type: :conversation, query: query)
    result[:personal][key] = filter.attributes.slice('id', 'account_id', 'user_id', 'name', 'filter_type', 'query')
  end
  # Legacy non-conversation rows are migration sentinels, not conversation queries.
  %w[contact report].each do |type|
    filter = CustomFilter.create!(account: accounts['A'], user: users['alice'], name: "Legacy #{type}",
      filter_type: type, query: { payload: [] })
    result[:personal][type] = filter.attributes.slice('id', 'account_id', 'user_id', 'name', 'filter_type', 'query')
  end
end
# Incoming-message after_commit hooks may reopen a resolved conversation. Apply
# the fixture's final states only after that outer transaction has committed.
result[:conversations].each do |row|
  conversation = Conversation.find(row[:id])
  conversation.update!(status: row[:status])
  raise 'Fixture status mismatch' unless conversation.reload.status == row[:status]
end
puts "POCKET_FIXTURE=#{JSON.generate(result)}"
